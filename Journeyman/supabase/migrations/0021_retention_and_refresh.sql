-- Three things that are fine today and expensive at the traffic this is for.
--
-- None of them is a bug you can trip over now. All three are shaped so that
-- they get worse in proportion to success, which is the worst way for a problem
-- to be shaped -- it arrives exactly when there is least time to look at it.

-- ── 1. Finished sessions are working state, not a record ──────────────────
--
-- Every start writes a game_sessions row carrying the answer, and nothing has
-- ever deleted one. At thirty thousand players a day that is eleven million
-- rows a year, each with a JSON payload, to support a table whose entire job is
-- to hold a game that is currently being played.
--
-- game_results is the permanent record and is untouched by this. What goes is
-- the working copy, once it can no longer be resumed.
--
-- Kept for 30 days rather than deleted on completion: a result that looks wrong
-- is investigated by looking at the session that produced it, and "why did this
-- score happen" is a question that arrives days later, not minutes.
create or replace function public.prune_finished_sessions(p_keep_days integer default 30)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_deleted integer;
begin
  delete from public.game_sessions
  where status <> 'active'
    and finished_at < now() - make_interval(days => greatest(coalesce(p_keep_days, 30), 1));

  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$$;

revoke all on function public.prune_finished_sessions(integer) from public;
revoke all on function public.prune_finished_sessions(integer) from anon;
revoke all on function public.prune_finished_sessions(integer) from authenticated;
grant execute on function public.prune_finished_sessions(integer) to service_role;

-- An abandoned-looking session that was never finished is a different case: it
-- has no finished_at, so the clause above never reaches it. These are games
-- somebody walked away from mid-play, and they hold a daily slot open forever
-- because of the one-per-day index. Ninety days is long enough that nobody is
-- coming back.
create or replace function public.prune_stale_sessions(p_keep_days integer default 90)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_deleted integer;
begin
  delete from public.game_sessions
  where status = 'active'
    and started_at < now() - make_interval(days => greatest(coalesce(p_keep_days, 90), 1));

  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$$;

revoke all on function public.prune_stale_sessions(integer) from public;
revoke all on function public.prune_stale_sessions(integer) from anon;
revoke all on function public.prune_stale_sessions(integer) from authenticated;
grant execute on function public.prune_stale_sessions(integer) to service_role;

-- The delete needs an index or it is a sequential scan over the whole table,
-- which is the thing it exists to prevent.
create index if not exists game_sessions_finished_at
  on public.game_sessions (finished_at)
  where status <> 'active';

create index if not exists game_sessions_started_at
  on public.game_sessions (started_at)
  where status = 'active';


-- ── 2. Spent quota rows ───────────────────────────────────────────────────
--
-- One row per subject per day, and yesterday's is never read again -- the
-- allowance is keyed on the date, so an old row cannot be consumed. Smaller
-- than sessions and the same shape.
create or replace function public.prune_game_quota(p_keep_days integer default 14)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_deleted integer;
begin
  delete from public.game_quota
  where quota_date < current_date - greatest(coalesce(p_keep_days, 14), 1);

  get diagnostics v_deleted = row_count;
  return v_deleted;
end;
$$;

revoke all on function public.prune_game_quota(integer) from public;
revoke all on function public.prune_game_quota(integer) from anon;
revoke all on function public.prune_game_quota(integer) from authenticated;
grant execute on function public.prune_game_quota(integer) to service_role;

-- payment_events is deliberately not pruned. It is a financial record, it is
-- small -- one row per purchase or refund, not per game -- and the question it
-- answers is asked years later.


-- ── 3. The leaderboard refresh ────────────────────────────────────────────
--
-- 0007 scheduled it every minute. That is a full GROUP BY over the whole of
-- game_results, 1,440 times a day, forever, and it grows with the table. It was
-- reasonable when the board was the only one and results were few; it is now
-- the largest standing database cost here.
--
-- Every fifteen minutes instead. The all-time board is all-time -- it does not
-- meaningfully change in sixty seconds, the UI already says how old it is, and
-- the board people actually watch during a day is the daily one, which is read
-- live and is not a view at all.
--
-- An admin voiding a day still refreshes immediately: set_day_voided does its
-- own refresh, because that is the case where staleness is visible and wrong.
do $$
begin
  if not exists (select 1 from pg_available_extensions where name = 'pg_cron') then
    raise warning 'pg_cron unavailable: nothing is pruned and the leaderboard will not refresh. '
                  'Call the prune_* functions and refresh_leaderboard() from a scheduled job.';
    return;
  end if;

  create extension if not exists pg_cron;

  perform cron.unschedule('refresh-leaderboard')
  where exists (select 1 from cron.job where jobname = 'refresh-leaderboard');

  perform cron.schedule(
    'refresh-leaderboard',
    '*/15 * * * *',
    $cron$select public.refresh_leaderboard();$cron$
  );

  -- Pruning runs nightly and off the hour, so it does not land with the
  -- rate-limit prune or a refresh.
  perform cron.unschedule('prune-sessions')
  where exists (select 1 from cron.job where jobname = 'prune-sessions');

  perform cron.schedule(
    'prune-sessions',
    '43 3 * * *',
    $cron$select public.prune_finished_sessions(), public.prune_stale_sessions(), public.prune_game_quota();$cron$
  );
exception
  when insufficient_privilege or undefined_file then
    raise warning 'could not schedule retention: %', sqlerrm;
end
$$;
