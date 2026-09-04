-- Refresh the leaderboard on a schedule.
--
-- Separate from 0006 on purpose: the materialized view is the part that must
-- land everywhere, and pg_cron is an extension a hosted project may not have
-- enabled. A failure here would otherwise block the view itself, so this
-- degrades to a warning and leaves the refresh to be triggered another way.

do $$
begin
  if not exists (select 1 from pg_available_extensions where name = 'pg_cron') then
    raise warning 'pg_cron unavailable: the leaderboard will not refresh on its own. '
                  'Enable it in the Supabase dashboard, or call refresh_leaderboard() '
                  'from a scheduled job.';
    return;
  end if;

  create extension if not exists pg_cron;

  -- Unschedule first so re-running is a no-op rather than a duplicate job.
  perform cron.unschedule('refresh-leaderboard')
  where exists (select 1 from cron.job where jobname = 'refresh-leaderboard');

  -- Every minute. The refresh costs about 235ms against 500,000 results, so a
  -- minute of staleness buys back roughly 85ms on every single sidebar open.
  perform cron.schedule(
    'refresh-leaderboard',
    '* * * * *',
    $cron$select public.refresh_leaderboard();$cron$
  );
exception
  when insufficient_privilege or undefined_file then
    raise warning 'could not schedule the leaderboard refresh: %', sqlerrm;
end
$$;
