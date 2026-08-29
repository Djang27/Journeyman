-- Initial schema, converted verbatim from supabase_setup.sql.
--
-- Kept idempotent (create ... if not exists, drop policy if exists) because the
-- hosted project already has every object here. Applying it there is a no-op,
-- which is what lets local and production converge on the same file.

-- ============================================================
-- Journeyman — Supabase setup
-- Run this in: Supabase Dashboard → SQL Editor → New query
-- ============================================================

-- 1. game_results: one row per finished game
--
-- Every column here is written by App.js when a game ends and read back by the
-- Stats and History tabs in Sidebar.js. Keep the three in step: a column that
-- exists in only two of them fails silently, because the insert error is only
-- logged to the console and the game carries on looking fine.
create table if not exists public.game_results (
  id            uuid        default gen_random_uuid() primary key,
  user_id       uuid        references auth.users(id) on delete cascade not null,
  player_name   text        not null,
  result        text        not null check (result in ('win', 'loss')),
  wrong_guesses integer     not null default 0,
  num_teams     integer     not null default 0,
  time_seconds  integer,
  hint_used     boolean     not null default false,
  hard_mode     boolean     not null default false,
  score         integer     not null default 0,
  game_mode     text        not null default 'unlimited'
                            check (game_mode in ('daily', 'unlimited')),
  created_at    timestamptz default now() not null
);

-- Bring an existing project up to the schema above. `create table if not exists`
-- above is a no-op once the table exists, so projects created before these
-- columns were added need them backfilled explicitly. Safe to re-run.
alter table public.game_results add column if not exists time_seconds integer;
alter table public.game_results add column if not exists hint_used    boolean not null default false;
alter table public.game_results add column if not exists hard_mode    boolean not null default false;
alter table public.game_results add column if not exists score        integer not null default 0;
alter table public.game_results add column if not exists game_mode    text    not null default 'unlimited';

alter table public.game_results drop constraint if exists game_results_game_mode_check;
alter table public.game_results
  add constraint game_results_game_mode_check
  check (game_mode in ('daily', 'unlimited'));

alter table public.game_results enable row level security;

-- Postgres has no `create policy if not exists`, so every policy is dropped and
-- recreated. That also makes this file the single source of truth: editing a
-- policy here and re-running applies the new definition, rather than silently
-- leaving an older one in place.
drop policy if exists "Users can read their own results" on public.game_results;
create policy "Users can read their own results"
  on public.game_results for select
  using (auth.uid() = user_id);

drop policy if exists "Users can insert their own results" on public.game_results;
create policy "Users can insert their own results"
  on public.game_results for insert
  with check (auth.uid() = user_id);


-- 2. profiles: public display names (used by the leaderboard)
create table if not exists public.profiles (
  id           uuid references auth.users(id) on delete cascade primary key,
  display_name text
);

alter table public.profiles enable row level security;

drop policy if exists "Profiles are publicly readable" on public.profiles;
create policy "Profiles are publicly readable"
  on public.profiles for select
  using (true);

drop policy if exists "Users can insert their own profile" on public.profiles;
create policy "Users can insert their own profile"
  on public.profiles for insert
  with check (auth.uid() = id);

drop policy if exists "Users can update their own profile" on public.profiles;
create policy "Users can update their own profile"
  on public.profiles for update
  using (auth.uid() = id);


-- 3. Auto-create a profile row whenever a new user signs up
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, display_name)
  values (
    new.id,
    coalesce(
      new.raw_user_meta_data->>'display_name',
      split_part(new.email, '@', 1)
    )
  )
  on conflict (id) do nothing;
  return new;
end;
$$ language plpgsql security definer set search_path = '';

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();


-- 4. Leaderboard: per-user aggregates, readable by everyone.
--
-- This has to read across every user's game_results while the RLS policy above
-- keeps the individual rows private. That is a deliberate privilege escalation,
-- and Postgres offers two ways to write it:
--
--   * A plain view, which silently runs with its owner's rights. Supabase flags
--     this (security_definer_view) because the escalation is invisible at the
--     call site -- nothing about `from leaderboard` hints that RLS was skipped.
--   * A security definer function, where the escalation is declared in the
--     definition, greppable, and pinned to an empty search_path so a caller
--     cannot hijack it by creating a shadowing object earlier in their path.
--
-- The second is why the view is gone. Note that `security_invoker = true` is not
-- an available fix: it would apply the caller's RLS to game_results and collapse
-- the leaderboard to a single row containing only the caller -- and to nothing
-- at all for signed-out visitors.
drop view if exists public.leaderboard;

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
    p.id,
    coalesce(p.display_name, 'Anonymous'),
    count(*),
    sum(case when gr.result = 'win'  then 1 else 0 end),
    sum(case when gr.result = 'loss' then 1 else 0 end),
    coalesce(sum(gr.score), 0),
    round(
      sum(case when gr.result = 'win' then 1.0 else 0.0 end)
      / nullif(count(*), 0) * 100
    )::integer
  from public.profiles p
  join public.game_results gr on gr.user_id = p.id
  group by p.id, p.display_name
  -- Ordinals rather than names: the RETURNS TABLE columns are in scope inside
  -- the body, so a bare `total_score` here would be ambiguous. 6 is total_score
  -- and 4 is wins, matching the "Pts" and "W" columns Sidebar.js renders.
  order by 6 desc, 4 desc
  -- Clamped, so a caller cannot ask for the entire table.
  limit least(greatest(coalesce(limit_count, 10), 1), 100);
$$;

-- Granted explicitly rather than inherited from public, so the elevated path has
-- exactly one door and it is visible here.
revoke all on function public.get_leaderboard(integer) from public;
grant execute on function public.get_leaderboard(integer) to anon, authenticated;
