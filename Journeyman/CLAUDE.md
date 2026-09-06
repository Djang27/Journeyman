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
  daily_cache.py        today's puzzle, held in process
  entitlements.py       what someone bought, provider-agnostic
  payment_events.py     the log that makes a webhook safe to receive twice
  quota.py              the free-tier allowance
  stripe_billing.py     the only file that knows what Stripe is
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

**Phase 3 is in progress.** Payments are Stripe, one-time, $9.99 lifetime.
Fulfilment happens on a signature-verified webhook and nowhere else -- the
Checkout redirect is client-controlled and proves nothing. Identity comes from
`client_reference_id`, never email. The webhook is exempt from maintenance mode
and rate limiting, because a rejected webhook is a payment event lost.

 The free tier is five unlimited games a day,
counted atomically in Postgres (migration 0012) and keyed on a verified user id
or a hashed address — anonymous play is metered because a quota keyed only on
accounts is bypassed by signing out. The daily puzzle is never charged. Refusal
is `402`, not `429`: a rate limit resolves itself in seconds, this does not.
`quota.Entitlements` is the seam `feat/stripe-entitlements` fills; today
`FreeTierOnly` always returns False.

**Phase 4 is in progress.** The headline leaderboard ranks *today's puzzle*,
not all-time totals: summing scores measures volume, and with unlimited mode the
all-time winner is whoever played most. Ties break on time. `shadowbanned` on
profiles is filtered from every board and is not readable by clients.

**Phase 2 is complete.** Materialized leaderboard, rate limiting, structured
logging, synthetic smoke test, maintenance mode, admin tools, and the daily
puzzle cached in process. The frontend degrades rather than throwing when
Supabase is unconfigured, and a game in progress survives a refresh. See
`docs/ROADMAP.md` for the fallback table, which now records what was verified
rather than what was hoped.

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
- **Code that needs a migration must not merge with it.** Vercel deploys on
  push to `main` immediately; the migration workflow runs in parallel and takes
  minutes. Ship the migration alone, wait for it to apply, then ship the code.
  This is what "additive database changes merge early and alone" is for --
  ignoring it put production on a `consume_quota` that did not exist yet.
- **Stripe has products and prices, and the dashboard shows the product id
  first.** Pasting a `prod_` where `STRIPE_PRICE_ID` wants a `price_` is a 500
  at checkout. `/api/billing/config` reports `status: price_is_a_product` for
  exactly this.
- **Postgres will not subtract a column from a table-level SELECT grant.**
  `revoke select (col) ... from anon` silently does nothing while the table
  grant stands. Revoke the table and grant the wanted columns back -- 0017 does
  this so `shadowbanned` stays invisible.
- **A quota is not a rate limit.** The limiter may be approximate — its worst
  case is 2x across a window boundary, which costs nothing. The quota is about
  money, so it consumes in one atomic statement. Do not merge the two.
- **Module-level state leaks between tests.** The puzzle cache and the rate
  limiter and the quota store all count per process, so one test's requests
  change what the next test sees. The `client` fixture resets all three;
  anything else process-global needs the same treatment.
- **`frontend/src/lib/supabase.js` is on the import path of everything.**
  `index.js -> App.js -> lib/supabase`. Anything thrown at module scope there
  happens before React mounts and shows a blank page, not an error. It returns
  a null client and `authAvailable: false` instead; guard new call sites.
- **CI is path-filtered to `Journeyman/**`.** A PR touching nothing under it will
  never run the required checks and blocks forever waiting.

## Operations

All four deployment secrets are configured and each was verified by running the
thing it enables, not by observing that it was set:

- `PRODUCTION_URL` -> the smoke test plays a real game against production every
  30 minutes and on every backend merge
- `SENTRY_DSN` (Vercel) -> `/api/health` reports `error_reporting_status:
  enabled`
- `SUPABASE_PRODUCTION_URL` / `SUPABASE_PRODUCTION_SERVICE_ROLE_KEY` -> the
  weekly top-up runs Mondays. **The calendar now runs to 2027-01-03.**

Two things worth knowing when one of these looks broken:

- **A Vercel environment variable only applies to new deployments.** Setting one
  does nothing to the build already running; it needs a redeploy. This cost an
  hour of looking for a misconfiguration that did not exist.
- **`SUPABASE_PRODUCTION_URL` must be the bare project URL**, no trailing slash
  and no path. Anything else makes PostgREST return `PGRST125: Invalid path
  specified in request URL`, which reads like a permissions problem and is not.
  The schedule workflow dry-runs first, so this fails before it writes.

Payments need four more, and checkout is not offered without them:
`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID`, and
optionally `PUBLIC_URL`. A deployment missing them shows no buy button rather
than a broken one.

`ADMIN_TOKEN` is deliberately unset. The admin routes are closed when it is
missing rather than open, so leaving it unset disables them.
