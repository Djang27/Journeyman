-- What someone has bought.
--
-- Deliberately provider-agnostic and deliberately alone: no Stripe anywhere in
-- here, and no code in this migration's branch reads it. Migration 0012 shipped
-- together with the code that called it, Vercel deployed before the migration
-- applied, and production spent minutes calling a function that did not exist.
-- The schema goes first from now on.
--
-- ## Current state, not an event log
--
-- One row per person per product, with revoked_at rather than a delete, so
-- "why does this account have access?" and "why did it stop?" both have
-- answers. The append-only record of *payments* is a separate table that
-- arrives with the webhook that needs it -- these are different lifetimes: a
-- payment event is immutable history, an entitlement is current truth derived
-- from it.
--
-- ## Revoked, not deleted
--
-- Same reasoning as game_results.voided. A refund six months later must not
-- erase the fact that somebody paid, and the moment you want the history is the
-- moment you least expected to need it.

create table if not exists public.entitlements (
  user_id          uuid        not null references auth.users(id) on delete cascade,
  -- 'journeyman_lifetime' today. A column rather than a boolean on profiles
  -- because a second product should not require a schema change.
  product          text        not null,
  granted_at       timestamptz not null default now(),
  -- Null means active. A timestamp means it was taken away, and why.
  revoked_at       timestamptz,
  revoked_reason   text,
  -- Where it came from: 'stripe', or 'manual' for a comp or a goodwill grant.
  source           text        not null default 'manual',
  -- The payment or session id, so a grant can be traced back to money.
  source_reference text,
  primary key (user_id, product)
);

-- The only question asked on the hot path: is this person entitled right now.
create index if not exists entitlements_active
  on public.entitlements (user_id, product)
  where revoked_at is null;

-- Server only. A client that could write here would grant itself the product.
alter table public.entitlements enable row level security;


-- Is this person entitled to this product right now.
create or replace function public.has_entitlement(
  p_user_id uuid,
  p_product text
)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.entitlements e
    where e.user_id = p_user_id
      and e.product = p_product
      and e.revoked_at is null
  );
$$;


-- Grant, or un-revoke a previous grant.
--
-- Idempotent on (user_id, product): paying twice, or a webhook delivered twice,
-- must not create a second row or fail. It updates the provenance to the most
-- recent payment and clears any revocation, which is what "they bought it
-- again after a refund" should mean.
create or replace function public.grant_entitlement(
  p_user_id          uuid,
  p_product          text,
  p_source           text default 'manual',
  p_source_reference text default null
)
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.entitlements as e (user_id, product, source, source_reference)
  values (p_user_id, p_product, p_source, p_source_reference)
  on conflict (user_id, product) do update
    set revoked_at       = null,
        revoked_reason   = null,
        granted_at       = now(),
        source           = excluded.source,
        source_reference = excluded.source_reference;
end;
$$;


-- Take it away: a refund, or a chargeback.
--
-- Returns whether anything changed, so a duplicate refund webhook is
-- distinguishable from the first one without a separate read.
create or replace function public.revoke_entitlement(
  p_user_id uuid,
  p_product text,
  p_reason  text default null
)
returns boolean
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_changed integer;
begin
  update public.entitlements
  set revoked_at = now(),
      revoked_reason = p_reason
  where user_id = p_user_id
    and product = p_product
    and revoked_at is null;

  get diagnostics v_changed = row_count;
  return v_changed > 0;
end;
$$;


-- Revoked by name: default privileges grant EXECUTE to anon and authenticated
-- separately, and those survive a revoke from PUBLIC. A client able to call
-- grant_entitlement would simply give itself the product.
revoke all on function public.has_entitlement(uuid, text) from public;
revoke all on function public.has_entitlement(uuid, text) from anon;
revoke all on function public.has_entitlement(uuid, text) from authenticated;
grant execute on function public.has_entitlement(uuid, text) to service_role;

revoke all on function public.grant_entitlement(uuid, text, text, text) from public;
revoke all on function public.grant_entitlement(uuid, text, text, text) from anon;
revoke all on function public.grant_entitlement(uuid, text, text, text) from authenticated;
grant execute on function public.grant_entitlement(uuid, text, text, text) to service_role;

revoke all on function public.revoke_entitlement(uuid, text, text) from public;
revoke all on function public.revoke_entitlement(uuid, text, text) from anon;
revoke all on function public.revoke_entitlement(uuid, text, text) from authenticated;
grant execute on function public.revoke_entitlement(uuid, text, text) to service_role;
