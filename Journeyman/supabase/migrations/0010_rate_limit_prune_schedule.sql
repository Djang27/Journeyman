-- Prune spent rate-limit windows hourly.
--
-- Separate from 0009 for the same reason the leaderboard schedule is separate:
-- pg_cron is an extension a hosted project may not have enabled, and a failure
-- here must not block the limiter itself from landing.

do $$
begin
  if not exists (select 1 from pg_available_extensions where name = 'pg_cron') then
    raise warning 'pg_cron unavailable: rate limit counters will accumulate. '
                  'Call prune_rate_limit_counters() from a scheduled job.';
    return;
  end if;

  create extension if not exists pg_cron;

  perform cron.unschedule('prune-rate-limits')
  where exists (select 1 from cron.job where jobname = 'prune-rate-limits');

  perform cron.schedule(
    'prune-rate-limits',
    '17 * * * *',
    $cron$select public.prune_rate_limit_counters();$cron$
  );
exception
  when insufficient_privilege or undefined_file then
    raise warning 'could not schedule rate limit pruning: %', sqlerrm;
end
$$;
