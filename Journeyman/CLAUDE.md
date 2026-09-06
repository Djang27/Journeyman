# Journeyman

An NBA career-path guessing game. Players are shown a player's name and must name
each team they played for, in order. Daily puzzle plus an unlimited mode.

Live on Vercel. React frontend, Flask API, Supabase (Postgres + Auth).

## Layout

```
backend/
  app.py                routes: the session API, health, error handling
  sessions.py           the game engine -- the answer lives here, never on the wire
  supabase_store.py     SessionStore over PostgREST
  auth.py               Supabase token verification (JWKS)
  scoring.py            scoring rules, ported from the browser
  game_logic.py         guess grading
  generate_players.py   player selection; reads the curated pool, JSON as fallback
  puzzles_repo.py       daily puzzle scheduling
  players_repo.py       the players table
  validation.py         career checks that need no source to compare against
  career_builder.py     season rows -> ordered career with seasons
  br_source.py          the Basketball-Reference pool source
  build_pool.py         rebuild nba_players.json from the source (run by hand)
  import_players.py     load the pool into Postgres
  schedule_puzzles.py   fill the daily calendar
  rate_limit.py         application-level limiting
  observability.py      structured logging, Sentry
  smoke_test.py         plays a real game against a deployment
  ground_truth.py       score a candidate data source against verified careers
  nba_players.json      2,582 careers, CC0, rebuilt by build_pool.py
api/app.py              Vercel WSGI entrypoint
frontend/src/lib/api.js the session API client
supabase/migrations/    0001-0010, applied by CI on merge to main
docs/ROADMAP.md         the phased plan -- read before starting new work
docs/nba-data.md        player-data sourcing, and the source evaluation
```

## Commands

Run from the `Journeyman/` root unless noted.

```bash
pytest                       # backend suite
ruff check . && ruff format .
cd frontend && npm test
supabase start               # local Postgres + auth, in Docker
supabase db reset            # rebuild from migrations + seed
python backend/smoke_test.py --url <deployment>
```

Dev dependencies: `pip install -r backend/requirements-dev.txt`.

## Conventions

- **Branch per deployable idea.** If merging would leave the game broken, split it.
  `main` is protected: PR required, CI must pass.
- **Conventional commits** (`feat(api):`, `test(web):`, `chore:`, `style:`).
- **Formatting sweeps get their own commit**, never mixed into feature work.
- **Additive database changes merge early and alone.** Destructive ones wait
  behind a verification gate.
- **Every bug gets a failing test before the fix.**
- **No test hits a live third-party API.** Integration tests run against the
  local Supabase stack and skip when it is not up -- which means CI skips them,
  so a path exercised only against a fake is not really tested.

## Current state

**Phase 0 is complete.** The game is server-authoritative:

- The answer never leaves the server while a game is running. `/api/game/start`
  returns `num_teams`, not `teams`.
- Scoring happens in `backend/scoring.py`, timed from the server clock.
- `game_results` is writable only by the service role. Clients cannot insert,
  update or delete -- migration 0003.
- Identity comes from a verified Supabase token, never a request body. The
  project signs with asymmetric keys, so verification is against JWKS.
- The daily gate is a partial unique index, not localStorage.

**Phase 1 is complete.** The pool is 2,582 careers from a CC0
Basketball-Reference dataset, of which ~1,345 are promoted and ~771 are
recognisable enough for a daily. Puzzles are scheduled rows, seeded ~90 days
ahead.

**Phase 2 is complete.** Materialized leaderboard, rate limiting, structured
logging, synthetic smoke test, maintenance mode and admin tools. The frontend
degrades rather than throwing when Supabase is unconfigured, and a game in
progress survives a refresh. `perf/cache-daily` is the one item deliberately
left: see `docs/ROADMAP.md` for the fallback table, which now records what was
verified rather than what was hoped.

**Postgres down means the game is down.** Every start writes a session row
because the server holds the answer. Maintenance mode makes that a readable 503
instead of a 500; there is no design under which the daily plays without a
database.

## Gotchas

Things that have already cost time:

- **Do not add `pyproject.toml`.** Vercel's Python builder detects it and runs
  `uv lock`, which needs a `[project]` table, and the deploy fails before it
  reaches the app. Tool config lives in `pytest.ini` and `ruff.toml`.
- **A new Flask route needs a matching rewrite in `vercel.json`.** Without one it
  falls through to the SPA catch-all and returns `index.html`. Nothing in the
  test suite catches this -- the dev server routes by its own rules.
- **PostgREST caps a response at 1000 rows and says nothing.** Any query that can
  exceed that must page. This silently hid 345 promoted players from the
  scheduler and the game.
- **`revoke ... from public` is not enough on Supabase.** Default privileges
  grant `EXECUTE` to `anon` and `authenticated` separately; those survive and
  must be revoked by name.
- **Node and npm versions are load-bearing.** `package-lock.json` was generated
  by npm 11 (Node 24); npm 10 resolves the tree differently and its `npm ci`
  rejects the lock. CI and Vercel are pinned to Node 24. Do not regenerate the
  lock under npm 10 -- it silently drops `resolved` and `integrity`.
- **Season-granularity data cannot order a mid-season trade.** Both teams sit
  against the same season with nothing saying which came first. `career_builder`
  reads the neighbouring seasons and reports what it cannot resolve; those
  careers are held out of the rotation rather than guessed at.
- **Vercel builds every pushed commit.** A red preview may be for an older commit
  on a branch since fixed -- check which SHA it built.
- **`frontend/src/lib/supabase.js` is on the import path of everything.**
  `index.js -> App.js -> lib/supabase`. Anything thrown at module scope there
  happens before React mounts and shows a blank page, not an error. It returns
  a null client and `authAvailable: false` instead; guard new call sites.
- **CI is path-filtered to `Journeyman/**`.** A PR touching nothing under it will
  never run the required checks and blocks forever waiting.

## Outstanding, needs the owner

- `PRODUCTION_URL` secret -> enables the smoke test (currently skips)
- `SENTRY_DSN` in Vercel -> enables error reporting
- `SUPABASE_PRODUCTION_URL` / `SUPABASE_PRODUCTION_SERVICE_ROLE_KEY` secrets ->
  enables the weekly puzzle top-up. **The calendar runs out 2026-12-02**, after
  which the daily silently falls back to hashing the date.
