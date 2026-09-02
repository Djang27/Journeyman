-- Phase 0, step 1: the tables server-authoritative play needs.
--
-- Additive only. Nothing reads any of this yet -- the API still runs the old
-- stateless endpoints -- so this is safe to ship on its own.
--
-- The shape is deliberately multi-game (see docs/ROADMAP.md, "Anthology"):
-- `game_slug` and the two `jsonb` columns cost almost nothing now and save a
-- backfill across every accumulated row later.


-- 1. games: one row per game in the anthology.
create table if not exists public.games (
  slug        text        primary key,
  name        text        not null,
  is_live     boolean     not null default false,
  created_at  timestamptz not null default now()
);

insert into public.games (slug, name, is_live)
values ('journeyman', 'Journeyman', true)
on conflict (slug) do nothing;

-- Everyone may see which games exist; nothing here is sensitive.
alter table public.games enable row level security;

drop policy if exists "Games are publicly readable" on public.games;
create policy "Games are publicly readable"
  on public.games for select
  using (true);


-- 2. puzzles: the scheduled daily for each date.
--
-- This replaces `md5(date) % len(players)` in generate_players.py, where the
-- pool size is part of the key -- adding one player silently rewrites every
-- future date. Scheduled rows also allow no repeats, a hand-picked launch day,
-- deliberate difficulty pacing, and the archive sold in Phase 3.
--
-- `payload` is jsonb rather than typed columns so a second game, whose puzzles
-- look nothing like a career path, needs no migration.
create table if not exists public.puzzles (
  game_slug    text        not null references public.games(slug) on delete cascade,
  puzzle_date  date        not null,
  payload      jsonb       not null,
  created_at   timestamptz not null default now(),
  primary key (game_slug, puzzle_date)
);

-- RLS on with NO policies is deliberate, and is the whole point of Phase 0:
-- `payload` contains the answer. anon and authenticated get nothing. Only the
-- service role -- which bypasses RLS, and which only the server holds -- reads
-- this. A policy added here later would put answers back on the wire.
alter table public.puzzles enable row level security;


-- 3. game_sessions: one row per game in progress or finished.
create table if not exists public.game_sessions (
  id           uuid        primary key default gen_random_uuid(),
  game_slug    text        not null references public.games(slug) on delete cascade,
  -- Nullable: anonymous play works today and must keep working. Anonymous daily
  -- gating leans on a device id instead, which is weaker and accepted.
  user_id      uuid        references auth.users(id) on delete cascade,
  mode         text        not null check (mode in ('daily', 'unlimited')),
  -- Null for unlimited. For daily, the composite foreign key below ties it to a
  -- real scheduled puzzle.
  puzzle_date  date,
  -- The answer, held server-side for the life of the session. This column is
  -- the reason the table denies all client access.
  answer       jsonb       not null,
  -- Guesses so far, and their colours. Appended to by /api/game/guess.
  state        jsonb       not null default '{}'::jsonb,
  status       text        not null default 'active'
                           check (status in ('active', 'won', 'lost', 'abandoned')),
  -- Server clock, so elapsed time cannot be forged by the browser.
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,

  -- A daily session must point at a scheduled puzzle. Postgres skips a composite
  -- foreign key when any column is null (MATCH SIMPLE), so unlimited sessions --
  -- which have no puzzle_date -- pass unchecked while daily ones are enforced.
  constraint game_sessions_puzzle_fkey
    foreign key (game_slug, puzzle_date)
    references public.puzzles (game_slug, puzzle_date)
    on delete set null,

  -- A finished session must record when, and an active one must not.
  constraint game_sessions_finished_at_matches_status
    check ((status = 'active') = (finished_at is null))
);

-- One daily attempt per player per game, enforced by the database rather than by
-- localStorage. Partial, because unlimited sessions repeat freely and anonymous
-- sessions cannot be attributed.
create unique index if not exists game_sessions_one_daily_per_user
  on public.game_sessions (game_slug, user_id, puzzle_date)
  where mode = 'daily' and user_id is not null;

-- Resuming an interrupted game: find the caller's active session cheaply.
create index if not exists game_sessions_active_by_user
  on public.game_sessions (user_id, game_slug)
  where status = 'active';

-- Same reasoning as puzzles: `answer` lives here, so no policies. Service role
-- only.
alter table public.game_sessions enable row level security;


-- 4. game_slug on game_results, so results and leaderboards are per-game.
alter table public.game_results
  add column if not exists game_slug text not null default 'journeyman'
  references public.games(slug);

-- Existing rows predate the anthology and are all Journeyman; the default above
-- backfills them. Kept as a default so the Phase 0 API can omit it.
create index if not exists game_results_user_game_created
  on public.game_results (user_id, game_slug, created_at desc);
