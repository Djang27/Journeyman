-- Past dailies, playable by people who bought the game.
--
-- Schema only, and alone: nothing reads 'archive' until the next branch. 0012
-- shipped with its caller and production spent minutes calling a function that
-- did not exist yet, which is what this ordering avoids.
--
-- ## Why the leaderboard must not count these
--
-- The archive is roughly ninety puzzles deep and grows daily. If an archive win
-- scored like a daily, ten dollars would buy ninety games' worth of points and
-- the top of the leaderboard would be a list of people who paid, in order of
-- how much spare time they had. A leaderboard where money buys rank is not a
-- leaderboard.
--
-- So archive results are recorded -- they belong in a player's own history and
-- stats -- and excluded from the ranking. That split is the whole point of
-- doing this in the same migration as the mode itself: adding the mode without
-- excluding it would silently corrupt the ranking on the first purchase.
--
-- ## One attempt each
--
-- Same rule as the daily, for the same reason. A replayable puzzle with a
-- recorded score is a score you can grind rather than earn.

-- game_mode is constrained to a list, so a new mode is a constraint change.
alter table public.game_results drop constraint if exists game_results_game_mode_check;

alter table public.game_results
  add constraint game_results_game_mode_check
  check (game_mode in ('daily', 'unlimited', 'archive'));


-- One attempt per player per archived date. Partial, matching the daily index:
-- anonymous sessions cannot be attributed, and the archive requires an account
-- anyway since it requires an entitlement.
create unique index if not exists game_sessions_one_archive_per_user
  on public.game_sessions (game_slug, user_id, puzzle_date)
  where mode = 'archive' and user_id is not null;


-- Rebuilt to exclude archive results. A materialized view's query cannot be
-- changed in place.
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
  -- Bought, not earned. See the note at the top of this migration.
  and gr.game_mode <> 'archive'
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
