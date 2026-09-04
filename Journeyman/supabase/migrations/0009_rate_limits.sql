-- Counters for application-level rate limiting.
--
-- Postgres rather than Redis, deliberately. The Phase 3 quota -- five free
-- games a day -- is durable state tied to an account and has to be
-- transactional with session creation; in Redis an eviction would hand someone
-- free games. So Postgres is carrying rate-limit-shaped work regardless, and a
-- second system doing a similar job costs a secret, a failure mode and
-- something else to monitor for no benefit at this volume.
--
-- Redis earns its place when these writes become a meaningful share of database
-- load, or when unauthenticated floods need rejecting without touching Postgres
-- at all. The Python side is behind an interface so that is a swap, not a
-- rewrite.
--
-- This is the middle of three layers and cannot do the others' jobs: a
-- volumetric attack has already cost you by the time your code runs, and only an
-- edge (Cloudflare) can refuse it.

create table if not exists public.rate_limit_counters (
  -- What is being limited, e.g. 'game_start:user:<uuid>' or
  -- 'guess:ip:<sha256 prefix>'. Opaque here on purpose: the caller decides what
  -- deserves its own budget.
  bucket        text        not null,
  -- Start of the fixed window this count belongs to.
  window_start  timestamptz not null,
  count         integer     not null default 0,
  primary key (bucket, window_start)
);

-- Old windows are dead weight the moment their window passes.
create index if not exists rate_limit_counters_expiry
  on public.rate_limit_counters (window_start);

-- Server only. A client that could write here could reset its own limits.
alter table public.rate_limit_counters enable row level security;


-- Count one request against a bucket and say whether it is allowed.
--
-- Atomic in a single statement: two concurrent requests cannot both read the
-- same count and both decide they are under the limit, which is the failure a
-- read-then-write implementation has and only shows up under exactly the load
-- the limiter exists for.
--
-- Fixed windows rather than sliding: simpler, one row per bucket per window, and
-- the worst case is a caller landing 2x the limit across a window boundary.
-- That is a known and bounded cost, chosen over the extra machinery.
create or replace function public.consume_rate_limit(
  p_bucket         text,
  p_window_seconds integer,
  p_max_requests   integer
)
returns table (allowed boolean, used integer, resets_at timestamptz)
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_window_start timestamptz;
  v_count        integer;
begin
  if p_window_seconds <= 0 or p_max_requests <= 0 then
    raise exception 'window and limit must both be positive';
  end if;

  -- Truncate now() to the start of its window, so every request in the same
  -- window lands on the same row.
  v_window_start := to_timestamp(
    floor(extract(epoch from now()) / p_window_seconds) * p_window_seconds
  );

  insert into public.rate_limit_counters (bucket, window_start, count)
  values (p_bucket, v_window_start, 1)
  on conflict (bucket, window_start)
    do update set count = public.rate_limit_counters.count + 1
  returning public.rate_limit_counters.count into v_count;

  return query
  select
    v_count <= p_max_requests,
    v_count,
    v_window_start + make_interval(secs => p_window_seconds);
end;
$$;

revoke all on function public.consume_rate_limit(text, integer, integer) from public;
revoke all on function public.consume_rate_limit(text, integer, integer) from anon;
revoke all on function public.consume_rate_limit(text, integer, integer) from authenticated;
grant execute on function public.consume_rate_limit(text, integer, integer) to service_role;


-- Windows older than a day are unreachable: no request can land in them again.
create or replace function public.prune_rate_limit_counters()
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_deleted integer;
begin
  delete from public.rate_limit_counters
  where window_start < now() - interval '1 day';
  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$$;

revoke all on function public.prune_rate_limit_counters() from public;
revoke all on function public.prune_rate_limit_counters() from anon;
revoke all on function public.prune_rate_limit_counters() from authenticated;
grant execute on function public.prune_rate_limit_counters() to service_role;
