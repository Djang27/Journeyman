-- Rank by today's puzzle, not by an all-time total.
--
-- Summing scores measures volume, not skill. With unlimited mode the winner is
-- whoever played most, and it compounds: somebody joining in month six can
-- never catch a week-one player no matter how well they play. A daily board is
-- cheap, gives everyone a fresh shot each morning, and makes today's puzzle the
-- thing people talk about.
--
-- ## Not a materialized view
--
-- The all-time board is materialized because it aggregates the whole table. This
-- one reads a single day, and 0011 already indexed (game_slug, puzzle_date), so
-- the query is bounded by one day's play however long the game runs. A view
-- would buy nothing and cost staleness on the board people are watching change.
--
-- ## Shadowbanning, not banning
--
-- A cheater told they are banned makes another account. One who quietly stops
-- appearing on boards usually does not, and the results stay in their own
-- history, so nothing about their experience changes. Filtered from every board
-- rather than only this one -- a flag that covers one board is a flag somebody
-- will forget to apply to the next.

alter table public.profiles
  add column if not exists shadowbanned boolean not null default false;

comment on column public.profiles.shadowbanned is
  'Excluded from every leaderboard, silently. Their own history is unaffected.';

-- The flag itself is not readable by clients, which is the whole point.
--
-- profiles carries a "publicly readable" RLS policy, so without this a
-- shadowbanned player could select their own row and find out -- and a
-- shadowban somebody can detect is just a ban with extra steps. Column-level,
-- so the rest of the row stays public: the boards need display_name.
--
-- Revoke the table then grant the columns back, rather than revoking the one
-- column. Postgres will not subtract a column from a table-level SELECT grant:
-- the table grant wins and the column revoke silently does nothing, which is
-- exactly what happened the first time this was written.
--
-- Safe because nothing reads profiles directly. Both leaderboard functions are
-- security definer and bypass these grants entirely.
--
-- A column added later is not granted by this, which is the right default: a
-- new column on profiles should have to be made public deliberately.
revoke select on public.profiles from anon;
revoke select on public.profiles from authenticated;
grant select (id, display_name) on public.profiles to anon;
grant select (id, display_name) on public.profiles to authenticated;

-- Ties break on time. Two people with the same score have not played equally
-- well -- one of them was faster, and the score has already rounded that away.
create index if not exists game_results_daily_ranking
  on public.game_results (game_slug, puzzle_date, score desc, time_seconds)
  where game_mode = 'daily' and not voided;


create or replace function public.get_daily_leaderboard(
  p_puzzle_date date,
  limit_count   integer default 10
)
returns table (
  id            uuid,
  display_name  text,
  score         integer,
  time_seconds  integer,
  result        text,
  hard_mode     boolean
)
language sql
stable
security definer
set search_path = ''
as $$
  select
    p.id,
    coalesce(p.display_name, 'Anonymous'),
    gr.score,
    gr.time_seconds,
    gr.result,
    gr.hard_mode
  from public.game_results gr
  join public.profiles p on p.id = gr.user_id
  where gr.game_slug = 'journeyman'
    and gr.game_mode = 'daily'
    and gr.puzzle_date = p_puzzle_date
    and not gr.voided
    and not p.shadowbanned
  -- Score first, then the faster player, then whoever got there first.
  order by gr.score desc, gr.time_seconds asc nulls last, gr.created_at asc
  limit least(greatest(coalesce(limit_count, 10), 1), 100);
$$;

revoke all on function public.get_daily_leaderboard(date, integer) from public;
grant execute on function public.get_daily_leaderboard(date, integer) to anon, authenticated;


-- Where a caller sits on today's board, which is the question somebody outside
-- the top ten actually has. Computed rather than found by paging the board.
create or replace function public.daily_rank(
  p_puzzle_date date,
  p_user_id     uuid
)
returns table (rank integer, score integer, players integer)
language sql
stable
security definer
set search_path = ''
as $$
  with board as (
    select
      gr.user_id,
      gr.score,
      row_number() over (
        order by gr.score desc, gr.time_seconds asc nulls last, gr.created_at asc
      )::integer as position,
      count(*) over ()::integer as total
    from public.game_results gr
    join public.profiles p on p.id = gr.user_id
    where gr.game_slug = 'journeyman'
      and gr.game_mode = 'daily'
      and gr.puzzle_date = p_puzzle_date
      and not gr.voided
      and not p.shadowbanned
  )
  select position, score, total from board where user_id = p_user_id;
$$;

revoke all on function public.daily_rank(date, uuid) from public;
grant execute on function public.daily_rank(date, uuid) to anon, authenticated;


-- The all-time board gets the same filter. A flag that covers one board is a
-- flag somebody forgets to apply to the next one.
drop materialized view if exists public.leaderboard_totals cascade;

create materialized view public.leaderboard_totals as
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
where not gr.voided
  and gr.game_mode <> 'archive'
  and not p.shadowbanned
group by p.id, p.display_name, gr.game_slug;

create unique index leaderboard_totals_key
  on public.leaderboard_totals (game_slug, user_id);

create index leaderboard_totals_ranking
  on public.leaderboard_totals (game_slug, total_score desc, wins desc);

revoke all on public.leaderboard_totals from anon, authenticated;


-- `cascade` dropped these with the view, so they are recreated verbatim.
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
  limit least(greatest(coalesce(limit_count, 10), 1), 100);
$$;

revoke all on function public.get_leaderboard(integer) from public;
grant execute on function public.get_leaderboard(integer) to anon, authenticated;


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

revoke all on function public.refresh_leaderboard() from public;
revoke all on function public.refresh_leaderboard() from anon;
revoke all on function public.refresh_leaderboard() from authenticated;
grant execute on function public.refresh_leaderboard() to service_role;


create or replace function public.set_day_voided(
  p_game_slug   text,
  p_puzzle_date date,
  p_voided      boolean,
  p_reason      text default null
)
returns integer
language plpgsql
security definer
set search_path = ''
as $$
declare
  v_changed integer;
begin
  update public.game_results
  set voided = p_voided,
      voided_reason = case when p_voided then p_reason else null end
  where game_slug = p_game_slug
    and puzzle_date = p_puzzle_date
    and voided is distinct from p_voided;

  get diagnostics v_changed = row_count;

  refresh materialized view concurrently public.leaderboard_totals;

  return v_changed;
end;
$$;

revoke all on function public.set_day_voided(text, date, boolean, text) from public;
revoke all on function public.set_day_voided(text, date, boolean, text) from anon;
revoke all on function public.set_day_voided(text, date, boolean, text) from authenticated;
grant execute on function public.set_day_voided(text, date, boolean, text) to service_role;
