-- The leaderboard stops scanning the whole table on every read.
--
-- `get_leaderboard` aggregated every row of game_results, for every user, to
-- return ten rows -- on each sidebar open. Measured against 500,000 results
-- across 20,000 players: 85ms and 67MB of buffers per call. At five million
-- rows that is closer to a second, and concurrent readers multiply it rather
-- than sharing the work. It is the most likely way a busy day becomes an outage.
--
-- A materialized view does the aggregation once per refresh instead of once per
-- reader. The cost is staleness: a player's newest game does not appear until
-- the next refresh. For a leaderboard that is an acceptable trade, and the
-- refreshed_at column below lets the UI say so rather than quietly lying.

create materialized view if not exists public.leaderboard_totals as
select
  p.id                                                          as user_id,
  coalesce(p.display_name, 'Anonymous')                         as display_name,
  gr.game_slug,
  count(*)                                                      as games_played,
  sum(case when gr.result = 'win' then 1 else 0 end)            as wins,
  sum(case when gr.result = 'loss' then 1 else 0 end)           as losses,
  coalesce(sum(gr.score), 0)                                    as total_score,
  round(
    sum(case when gr.result = 'win' then 1.0 else 0.0 end)
    / nullif(count(*), 0) * 100
  )::integer                                                    as win_rate,
  max(gr.created_at)                                            as last_played_at,
  now()                                                         as refreshed_at
from public.profiles p
join public.game_results gr on gr.user_id = p.id
group by p.id, p.display_name, gr.game_slug;

-- Required for REFRESH ... CONCURRENTLY, which is what lets the refresh happen
-- without blocking readers. Without it every refresh would take an exclusive
-- lock and the leaderboard would stall for exactly as long as the work takes.
create unique index if not exists leaderboard_totals_key
  on public.leaderboard_totals (game_slug, user_id);

create index if not exists leaderboard_totals_ranking
  on public.leaderboard_totals (game_slug, total_score desc, wins desc);


-- Read the view rather than the table. Same signature and column order, so the
-- Sidebar's rpc call is unchanged.
create or replace function public.get_leaderboard(limit_count integer default 10)
returns table (
  id            uuid,
  display_name  text,
  games_played  bigint,
  wins          bigint,
  losses        bigint,
  total_score   bigint,
  win_rate      integer
)
language sql
stable
security definer
set search_path = ''
as $$
  select
    l.user_id,
    l.display_name,
    l.games_played,
    l.wins,
    l.losses,
    l.total_score,
    l.win_rate
  from public.leaderboard_totals l
  where l.game_slug = 'journeyman'
  order by l.total_score desc, l.wins desc
  -- Clamped, so a caller cannot ask for the entire table.
  limit least(greatest(coalesce(limit_count, 10), 1), 100);
$$;

revoke all on function public.get_leaderboard(integer) from public;
grant execute on function public.get_leaderboard(integer) to anon, authenticated;


-- How stale the numbers are, so the UI can say "as of a minute ago" instead of
-- presenting a snapshot as live.
create or replace function public.leaderboard_refreshed_at()
returns timestamptz
language sql
stable
security definer
set search_path = ''
as $$
  select max(l.refreshed_at) from public.leaderboard_totals l;
$$;

revoke all on function public.leaderboard_refreshed_at() from public;
grant execute on function public.leaderboard_refreshed_at() to anon, authenticated;


-- Refreshing is a privileged operation -- it reads every result row, across all
-- users -- so it is a security definer function the server calls, rather than a
-- grant on the view itself.
create or replace function public.refresh_leaderboard()
returns void
language plpgsql
security definer
set search_path = ''
as $$
begin
  refresh materialized view concurrently public.leaderboard_totals;
end;
$$;

-- `revoke from public` is not enough on Supabase: default privileges grant
-- EXECUTE on functions in this schema to anon and authenticated, so those
-- grants survive and have to be removed by name. Without this, any visitor can
-- trigger a full re-aggregation -- 235ms of database work per call, on demand.
revoke all on function public.refresh_leaderboard() from public;
revoke all on function public.refresh_leaderboard() from anon;
revoke all on function public.refresh_leaderboard() from authenticated;
grant execute on function public.refresh_leaderboard() to service_role;

-- The view holds one row per user per game, aggregated from results the
-- individual rows of which stay private. Reading it directly is not granted;
-- get_leaderboard is the single door, as it was before.
revoke all on public.leaderboard_totals from anon, authenticated;
