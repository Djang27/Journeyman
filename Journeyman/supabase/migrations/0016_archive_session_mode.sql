-- game_sessions.mode was left out of 0015.
--
-- That migration added 'archive' to game_results.game_mode and rebuilt the
-- leaderboard to exclude it, and stopped there. game_sessions has its own
-- check constraint on its own mode column, so an archive session could not be
-- inserted at all: every attempt failed on the constraint and came back a 500.
--
-- It was not caught by the endpoint tests because those run against the
-- in-memory session store, which has no constraints. It was caught by playing
-- an archive game against real Postgres, which is the only place the rule
-- exists. That is the same gap CLAUDE.md already records about integration
-- tests skipping in CI -- a path exercised only against a fake is not tested.

alter table public.game_sessions drop constraint if exists game_sessions_mode_check;

alter table public.game_sessions
  add constraint game_sessions_mode_check
  check (mode in ('daily', 'unlimited', 'archive'));
