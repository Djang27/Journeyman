-- Every payment event we were told about, exactly once.
--
-- Providers redeliver. Stripe retries a webhook for up to three days, and a
-- redelivery is routine rather than exceptional -- a timeout on our side, a
-- deploy mid-request, or an operator replaying an event by hand. So "have I
-- already applied this?" has to be answerable, and the only reliable answer is
-- the provider's own event id.
--
-- ## Append-only, and separate from entitlements
--
-- Different lifetimes. A payment event is immutable history: it happened, and
-- no later refund unhappens it. An entitlement is current truth derived from
-- that history. Collapsing the two would mean a refund overwriting the record
-- of the purchase it refunds, which is exactly the question you need answered
-- when somebody disputes a charge.
--
-- ## Provider-agnostic
--
-- `provider` is a column. Nothing here knows what Stripe is, and the payload is
-- stored verbatim so a handler can be fixed and the event replayed rather than
-- lost because the code that parsed it was wrong.

create table if not exists public.payment_events (
  provider     text        not null,
  -- The provider's own id for the event, which is what makes a redelivery
  -- recognisable. Ours would not: we cannot tell two identical deliveries
  -- apart by anything we generate on receipt.
  event_id     text        not null,
  type         text        not null,
  received_at  timestamptz not null default now(),
  -- Null until a handler has finished with it. A row received but never
  -- processed is the shape of a bug worth being able to query for.
  processed_at timestamptz,
  -- What went wrong, if anything did. Kept so a failed event can be found and
  -- replayed rather than discovered by a customer email.
  error        text,
  -- Verbatim. A handler that parsed it wrongly can be fixed and re-run.
  payload      jsonb,
  primary key (provider, event_id)
);

-- Finding the events that arrived and never completed -- the reconciliation
-- job's whole question.
create index if not exists payment_events_unprocessed
  on public.payment_events (provider, received_at)
  where processed_at is null;

-- Server only. This table is a financial record.
alter table public.payment_events enable row level security;


-- Record an event, and say whether it is new.
--
-- The return value is the idempotency decision: true means this is the first
-- time and the caller should act on it, false means it has been seen and the
-- caller should do nothing but acknowledge. Doing this in one statement matters
-- for the same reason it does in the quota -- two concurrent deliveries of the
-- same event must not both be told they are first.
create or replace function public.record_payment_event(
  p_provider text,
  p_event_id text,
  p_type     text,
  p_payload  jsonb default null
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_inserted integer;
begin
  insert into public.payment_events (provider, event_id, type, payload)
  values (p_provider, p_event_id, p_type, p_payload)
  on conflict (provider, event_id) do nothing;

  get diagnostics v_inserted = row_count;
  return v_inserted > 0;
end;
$$;


-- Mark an event finished, or record why it was not.
create or replace function public.complete_payment_event(
  p_provider text,
  p_event_id text,
  p_error    text default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  update public.payment_events
  set processed_at = case when p_error is null then now() else null end,
      error = p_error
  where provider = p_provider
    and event_id = p_event_id;
end;
$$;


-- Events that arrived and never completed. A webhook whose handler threw, or
-- one that a deploy interrupted. The reconciliation job reads this.
create or replace function public.unprocessed_payment_events(
  p_provider text,
  p_limit    integer default 100
)
returns table (event_id text, type text, received_at timestamptz, error text, payload jsonb)
language sql
stable
security definer
set search_path = ''
as $$
  select e.event_id, e.type, e.received_at, e.error, e.payload
  from public.payment_events e
  where e.provider = p_provider
    and e.processed_at is null
  order by e.received_at
  limit least(greatest(coalesce(p_limit, 100), 1), 1000);
$$;


-- Revoked by name: default privileges grant EXECUTE to anon and authenticated
-- separately, and those survive a revoke from PUBLIC. A client able to write
-- here could forge a payment record.
revoke all on function public.record_payment_event(text, text, text, jsonb) from public;
revoke all on function public.record_payment_event(text, text, text, jsonb) from anon;
revoke all on function public.record_payment_event(text, text, text, jsonb) from authenticated;
grant execute on function public.record_payment_event(text, text, text, jsonb) to service_role;

revoke all on function public.complete_payment_event(text, text, text) from public;
revoke all on function public.complete_payment_event(text, text, text) from anon;
revoke all on function public.complete_payment_event(text, text, text) from authenticated;
grant execute on function public.complete_payment_event(text, text, text) to service_role;

revoke all on function public.unprocessed_payment_events(text, integer) from public;
revoke all on function public.unprocessed_payment_events(text, integer) from anon;
revoke all on function public.unprocessed_payment_events(text, integer) from authenticated;
grant execute on function public.unprocessed_payment_events(text, integer) to service_role;
