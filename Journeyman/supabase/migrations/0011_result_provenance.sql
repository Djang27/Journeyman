-- Make a result traceable, and voidable.
--
-- game_results records what happened but not which game it came from. That
-- leaves an obvious question unanswerable: a bad puzzle ships, and there is no
-- way to say which rows came from it. "Void today's daily" cannot be expressed.
--
-- Three columns fix that, and set up the per-day leaderboard in Phase 4:
--
--   session_id   which game produced this, for provenance
--   puzzle_date  which day's puzzle it was, so a day can be selected
--   voided       marked rather than deleted, so a mistake is reversible and
--                the row can still be explained afterwards
--
-- Additive: every column is nullable or defaulted, and nothing reads them yet.

alter table public.game_results
  add column if not exists session_id uuid references public.game_sessions(id) on delete set null;

alter table public.game_results
  add column if not exists puzzle_date date;

-- Soft, not hard. A hard delete of a day's play is unreviewable and
-- unrecoverable, and the moment you want it is the moment you are least sure.
alter table public.game_results
  add column if not exists voided boolean not null default false;

alter table public.game_results
  add column if not exists voided_reason text;

-- Selecting a day is the whole point of the column.
create index if not exists game_results_by_puzzle_date
  on public.game_results (game_slug, puzzle_date)
  where puzzle_date is not null;

-- Voided rows are the exception, so index them rather than the rest.
create index if not exists game_results_voided
  on public.game_results (game_slug, puzzle_date)
  where voided;


-- A voided result must not count. Rebuilt rather than altered because a
-- materialized view's query cannot be changed in place.
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
group by p.id, p.display_name, gr.game_slug;

create unique index leaderboard_totals_key
  on public.leaderboard_totals (game_slug, user_id);

create index leaderboard_totals_ranking
  on public.leaderboard_totals (game_slug, total_score desc, wins desc);

revoke all on public.leaderboard_totals from anon, authenticated;


-- `cascade` above dropped these with the view, so they are recreated verbatim.
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

-- Revoked by name: default privileges grant EXECUTE to anon and authenticated
-- separately, and those survive a revoke from PUBLIC.
revoke all on function public.refresh_leaderboard() from public;
revoke all on function public.refresh_leaderboard() from anon;
revoke all on function public.refresh_leaderboard() from authenticated;
grant execute on function public.refresh_leaderboard() to service_role;


-- Void or restore a day's results in one statement, and report how many moved.
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

  -- Without this the leaderboard keeps counting the voided day until the next
  -- scheduled refresh, which is exactly when someone is watching.
  refresh materialized view concurrently public.leaderboard_totals;

  return v_changed;
end;
$$;

revoke all on function public.set_day_voided(text, date, boolean, text) from public;
revoke all on function public.set_day_voided(text, date, boolean, text) from anon;
revoke all on function public.set_day_voided(text, date, boolean, text) from authenticated;
grant execute on function public.set_day_voided(text, date, boolean, text) to service_role;
