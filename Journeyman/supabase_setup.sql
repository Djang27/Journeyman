-- ============================================================
-- Journeyman — Supabase setup
-- Run this in: Supabase Dashboard → SQL Editor → New query
-- ============================================================

-- 1. game_results: one row per finished game
create table if not exists public.game_results (
  id            uuid        default gen_random_uuid() primary key,
  user_id       uuid        references auth.users(id) on delete cascade not null,
  player_name   text        not null,
  result        text        not null check (result in ('win', 'loss')),
  wrong_guesses integer     not null default 0,
  num_teams     integer     not null default 0,
  created_at    timestamptz default now() not null
);

alter table public.game_results enable row level security;

create policy "Users can read their own results"
  on public.game_results for select
  using (auth.uid() = user_id);

create policy "Users can insert their own results"
  on public.game_results for insert
  with check (auth.uid() = user_id);


-- 2. profiles: public display names (used by the leaderboard)
create table if not exists public.profiles (
  id           uuid references auth.users(id) on delete cascade primary key,
  display_name text
);

alter table public.profiles enable row level security;

create policy "Profiles are publicly readable"
  on public.profiles for select
  using (true);

create policy "Users can insert their own profile"
  on public.profiles for insert
  with check (auth.uid() = id);

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
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();


-- 4. Leaderboard view: aggregate wins/losses per user (no private game details exposed)
create or replace view public.leaderboard as
select
  p.id,
  coalesce(p.display_name, 'Anonymous')               as display_name,
  count(*)                                             as games_played,
  sum(case when gr.result = 'win'  then 1 else 0 end) as wins,
  sum(case when gr.result = 'loss' then 1 else 0 end) as losses,
  round(
    sum(case when gr.result = 'win' then 1.0 else 0.0 end)
    / nullif(count(*), 0) * 100
  )::integer                                           as win_rate
from public.profiles p
inner join public.game_results gr on p.id = gr.user_id
group by p.id, p.display_name
order by wins desc, win_rate desc;

grant select on public.leaderboard to anon, authenticated;
