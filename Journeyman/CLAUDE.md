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

**The daily has a shape.** Every date is scored against a curve rather than
taken from one ranking of the pool: Monday targets difficulty 1 and Saturday 4,
with a hard floor on fame every day of the week and a gentle tilt toward careers
that ended after 1990. The fame floor is what makes a daily fair -- a name
nobody knows is a lookup, not a hard puzzle -- and it excludes difficulty 5
entirely without naming it, because every rating of 5 requires fame 3 or worse.
`schedule_puzzles.py --redo-future` reapplies the rules to a calendar already
filled; it never touches today or the archive.

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
- **You cannot rewrite *to* a `/_vercel/*` path.** Those are served by Vercel's
  platform layer, which sits outside `vercel.json` rewrites, so
  `/stats/script.js -> /_vercel/insights/script.js` falls through to the SPA
  catch-all and returns `index.html` with a 200. The tell is the content type:
  `text/html` where a script belongs. Analytics has to be loaded from its real
  path, which means filter lists can block it.
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
- **`difficulty` and fame are different axes, and selection wants fame.**
  `difficulty_for` is fame plus path length, so a one-time All-Star with eight
  clubs rates a 3 -- and that is the best puzzle this game has, not the worst.
  Narrowing the pool on the composite drops exactly those. `fame_for` is the
  axis a player means when they say "I don't know any of these".
- **A computed column nobody reads is worth checking for.** `difficulty` was
  rated at import, stored, used by the daily scheduler, and silently ignored by
  `randomPlayer`, which drew uniformly over everything promoted. Roughly 44% of
  that pool is rated obscure, so most unlimited games served a name the player
  could not place. Nothing failed; the game was just not fun.
- **A soft preference cannot express a curve.** `plan(prefer=...)` sorted the
  pool once, which cannot say "Monday and Saturday want different players".
  `fit(player, date)` grades each pairing instead, and dates are filled greedily
  with recency as the tie-break.
- **Longevity is evidence of fame, not a substitute for it.** The middle
  games threshold was 400 -- about five seasons -- which let it carry a player
  into the most recognisable tier on no other evidence. Terry Dehere averaged
  exactly 8.0 over exactly 402 games with no All-Star selection, cleared both
  boundaries by a hair, and came out rated alongside Mitch Richmond. It is 600
  now, and `PROMOTION_CAREER_GAMES` is a separate constant at 400 -- the two
  decide different things, and moving them together would have dropped
  forty-five careers out of the playable pool as a side effect.
- **A scoring average is not a career.** Anything over 11 points a game landed
  in the most recognisable tier regardless of how briefly -- 14% of Big names,
  including Walter Berry at 205 games. The career-length floor is 300, about
  four seasons, with an exception for players still active: a short career is
  only forgettable once it is over, which is why Jaden Ivey belongs there and
  Berry does not.
- **Longevity can make somebody recognisable; it cannot make them a star.**
  The -2 for a long career could reach tier 0, where Durant and Rodman sit --
  Caldwell Jones got there on 6.2 points a game and Dave Greenwood on 10.2, for
  turning out eight hundred times. Tier 0 needs direct evidence now: All-Star
  selections, or a scoring average nobody achieves quietly.
- **Longevity rescues a low scorer into the wrong era.** Billy Paultz, 8.5 a
  game and last seen in 1985, rated level with Kevin Durant. Careers ending
  before 2000 take a one-tier nudge unless the player was an All-Star -- a
  selection is direct evidence people knew the name, which is what the nudge is
  guessing at in its absence.
- **Do not read `players.difficulty` to choose a puzzle.** It is written at
  import, so it is a snapshot of the rules on the day that import ran, and
  retuning them leaves every stored value stale -- silently, because a stale
  tier is still a valid tier. `difficulty.rate(row)` derives both halves; the
  column is for reporting.
- **Clear `__pycache__` between mutation checks.** Restoring a file with `cp`
  can leave bytecode that pytest still imports, so a "restored" run reports
  failures that are not there -- or worse, a mutated run reports passes.
- **Fame is not recognisability for old careers.** It is computed from scoring,
  longevity and All-Star selections, all of which a 1960s journeyman can clear
  while being a name almost nobody can place. Roughly one daily a week landed
  there. Hence the era tilt -- weighted *below* a tier mismatch, so an exactly
  right older career still beats a modern one from the wrong tier.
- **CI is path-filtered to `Journeyman/**`.** A PR touching nothing under it will
  never run the required checks and blocks forever waiting.

## Measurement

Four places, none of which need code:

- **Vercel → Observability** — function invocations and bandwidth. This is API
  traffic: every start, every guess.
- **Vercel → Web Analytics** — page views, referrers, devices. Wired via the
  `/_vercel/insights/script.js` tag in `public/index.html` rather than the
  `@vercel/analytics` package, whose peer range wants a newer TypeScript than
  react-scripts 5 pins.
- **Sentry → Insights** — request throughput and latency, sampled at 10%, so
  multiply by ten.
- **Supabase → Reports** — database and PostgREST request counts.

None of them counts *games*. That lives in `game_sessions` and `game_results`,
and it is the number worth acting on: players a day, completion rate, daily
versus unlimited. Nothing surfaces it yet.

## Retention and scheduled work

Four jobs run in Postgres via pg_cron (0007, 0010, 0021). `select jobname,
schedule from cron.job` lists them:

- `refresh-leaderboard` every 15 minutes. It was every minute, which is a full
  aggregate over all of `game_results` 1,440 times a day and grows with the
  table. The all-time board does not change in sixty seconds; the board people
  watch during a day is the daily one, which is read live and is not a view.
- `prune-rate-limits` hourly
- `prune-sessions` nightly, which also prunes quota. Finished sessions are kept
  30 days -- "why did this score happen" arrives days later, not minutes -- and
  never-finished ones 90.

`payment_events` is deliberately never pruned: it is a financial record, it is
one row per purchase rather than per game, and the question it answers is asked
years later.

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

`ADMIN_TOKEN` gates every admin route, and they are closed when it is missing
rather than open. Set it and the operator tools work: swap a bad puzzle, void
or restore a day, search accounts, and shadowban with a reason.

Shadowbanning hides an account from every leaderboard and tells it nothing --
a cheater who knows makes another account. Their own history and stats are
untouched. A reason is required to ban and cleared on unban, because a reason
that outlives its ban is a note nobody can interpret.
