# Journeyman roadmap

Getting the game to production for thousands of players. Phases are ordered by
dependency, not appeal — each makes the next cheaper, and doing them out of order
means redoing work.

Status legend: `[ ]` not started · `[~]` in progress · `[x]` done

---

## Groundwork — environments and workflow

Three environments, each with one job:

| Environment | Database | Used for | Cost |
|---|---|---|---|
| Local | Supabase CLI in Docker (`supabase start`) | Writing migrations, tests, iteration. Disposable. | Free |
| Preview | A second Supabase project, free tier | Wired to Vercel per-branch deploys. Real infra, fake data. | Free |
| Production | Supabase Pro | Real players. Reached only by merging to `main`. | $25/mo |

- [x] `test/characterize-existing` — pytest + ruff config, backend and frontend
      test suites, GitHub Actions CI
- [ ] `chore/tooling` — pre-commit hooks
- [ ] `chore/supabase-local` — Supabase CLI config, convert `supabase_setup.sql`
      to migration `0001`, `seed.sql`, local setup docs
- [ ] `chore/environments` — fail-fast config module; throw on missing Supabase
      env vars instead of logging; `.env.example` per package; **pin Python and
      Node versions** across local/CI/Vercel; env var reference doc
- [ ] `ci/github-actions` — verify migrations apply from empty; apply to prod on
      merge to `main`
- [ ] `chore/extract-repo` *(optional)* — `git filter-repo` Journeyman into its
      own repo, repoint Vercel root. Removes the need for CI path filters.

**Manual steps:** create the preview Supabase project; set Production and Preview
env values separately in Vercel; enable branch protection on `main`.

> **Vercel environment mapping.** Production builds come from the Production
> Branch (`main`) and serve the real domain; every other branch and PR produces a
> Preview deployment on a throwaway URL. They are only actually separate if the
> env vars differ — a variable added without scoping applies to all environments,
> which means **preview deployments of experimental branches read and write the
> real players' database**. Scope the existing Supabase vars to Production, then
> add the same names for Preview pointing at the preview project. Confirm
> Settings → Git → Production Branch is `main`.

> The **service role key** introduced in Phase 0 bypasses RLS entirely. It must
> never carry a `REACT_APP_` prefix — CRA inlines those into the public bundle.

---

## Phase 0 — server authority

**Blocks launch.** Retrofitting this after players have real scores means wiping
the leaderboard. Roughly one focused week.

The problems, all consequences of the same root cause:

| | Problem |
|---|---|
| Critical | `/new-game` ships the full `Teams` answer to the browser |
| Critical | Scores computed client-side, inserted with the anon key; RLS can't tell honest rows from invented ones |
| Critical | `/check-guess` holds no state — it grades a client-supplied answer |
| High | Daily-replay gate is `localStorage` |
| High | Elapsed time is a browser clock, and time dominates the score |

The fix — a session lifecycle:

1. `POST /api/game/start` — server checks entitlement, picks the player, writes a
   `game_sessions` row, returns only `{session_id, player_name, num_teams}`.
2. `POST /api/game/guess` — server loads the session, grades against the real
   answer, returns a colour and the wrong count. Rejects out-of-range positions,
   finished sessions, and re-guessing a solved slot.
3. Server ends the game, times it from `now() - started_at`, scores it, writes
   `game_results`, closes the session.
4. `revoke insert on game_results from authenticated`.

- [ ] `db/session-schema` — `games`, `puzzles`, `game_sessions`; `game_slug` on
      `game_results`. Additive only.
- [ ] `feat/session-api` — port scoring to Python; **scoring parity tests against
      the JS fixtures before switching anything**; session repository; the three
      endpoints; lifecycle tests; module-level player-pool cache
- [ ] `feat/session-frontend` — API client module; drive the game from the session
      API; drop `teams` from App state; remove the client-side result insert
- [ ] `chore/lock-down-writes` — revoke insert; unique index on daily results;
      delete legacy endpoints; remove `calculate_score` (keep `calculate_streaks`)

**Gate before `chore/lock-down-writes`:** play the preview deploy for a full day —
daily and unlimited, win and loss, signed in and out. A bug here loses real games.

Schema is multi-game from the start (see *Anthology* below):

```sql
create table games (
  slug text primary key, name text not null,
  is_live boolean not null default false
);

create table puzzles (
  game_slug text not null references games(slug),
  puzzle_date date not null,
  payload jsonb not null,            -- game-specific puzzle content
  primary key (game_slug, puzzle_date)
);

create table game_sessions (
  id uuid primary key default gen_random_uuid(),
  game_slug text not null references games(slug),
  user_id uuid references auth.users(id) on delete cascade,  -- null = anonymous
  mode text not null check (mode in ('daily', 'unlimited')),
  puzzle_date date,
  answer jsonb not null,             -- never leaves the server
  state jsonb not null default '{}',
  status text not null default 'active'
         check (status in ('active', 'won', 'lost', 'abandoned')),
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

-- one daily attempt per player per game, enforced by the database
create unique index on game_sessions (game_slug, user_id, puzzle_date)
  where mode = 'daily' and user_id is not null;
```

`payload`/`answer` are `jsonb` so a second game needs no migration. `user_id` is
nullable because anonymous play works today and should keep working.

---

## Phase 1 — data foundation

Kills the rate-limit problem permanently. **See `docs/nba-data.md` for the
sourcing investigation** — that document drives this phase.

- [ ] `feat/players-table` — `players` table with curation columns; seed from the
      existing JSON first; read pool from DB with JSON as fallback; bulk
      historical backfill; puzzle scheduler; **replace `md5(date) % len(players)`
      with scheduled `daily_puzzles` rows**
- [ ] `feat/ingest-delta` — weekly in-season roster delta job; scheduling and
      failure alerting; pipeline runbook

---

## Phase 2 — scale and resilience

Independent branches, mergeable in any order. Thousands of users is a small load
(~3 writes/sec at 30k daily players); the risk is caching and blast radius, not
throughput.

- [ ] `perf/cache-daily` — **highest leverage on this list.** The daily puzzle is
      identical for everyone; cache it at the edge until midnight ET and one DB
      read serves 100k people
- [ ] `perf/leaderboard-mv` — materialized view + `pg_cron` 60s refresh.
      `get_leaderboard` currently aggregates the whole table on every sidebar open
- [ ] `feat/rate-limits` — token bucket on `user_id`, hashed-IP fallback.
      ~30/hour on start, ~120/min on guess
- [ ] `ops/observability` — Sentry on frontend and API; health endpoint; uptime
      monitor; Cloudflare in front of the domain
- [ ] `ops/degraded-mode` — read-only flag; client-side pending-result buffer that
      flushes on reconnect; admin endpoints to swap a puzzle and void a day

**Fallbacks.** The governing rule: *a user request must never touch a third party.*

| When | What happens |
|---|---|
| Ingestion API blocked | Nothing user-facing. Puzzles come from Postgres. |
| Postgres down | Daily works from edge cache; results buffer client-side; unlimited falls back to bundled JSON |
| Auth down | Anonymous play continues |
| Traffic spike | Degraded mode: writes and unlimited off, daily still playable |
| Bad puzzle ships | Admin swap for tomorrow, void today's results |

---

## Phase 3 — quota and payments

Depends on Phase 0; a quota is meaningless if the client can bypass it.

- [ ] `feat/daily-quota` — `daily_quota(user_id, game_slug, date)`; atomic consume
      in the start endpoint; remaining-games UI
- [ ] `feat/stripe-entitlements` — entitlement column; Checkout; webhook handler
      (idempotent on event id); hosted portal; archive gating

Pricing: **5 free unlimited games/day** (not 10 — you can loosen a cap, tightening
one reads as a takeaway). **Daily puzzle free forever, no account** — it's the
acquisition funnel and share loop. **$9.99 one-time lifetime unlock** as the
primary offer; puzzle audiences convert better on one-time purchases and it
removes churn management entirely. Bundle the **archive of past dailies** — that's
the genuinely valuable thing, not just removing a wall.

Skip ads. This audience runs blockers (there is a commit in this repo titled
"Fix share button hidden by ad blockers"), and revenue at 10k DAU would be
$20–60/month.

---

## Phase 4 — global leaderboard

Only trustworthy after Phase 0.

- [ ] `feat/daily-leaderboard` — per-puzzle-date function; shadowban flag filtered
      from all boards; daily board as headline with all-time and streaks as tabs

**Rank by today's puzzle, not all-time total.** Summing scores measures volume,
not skill — with unlimited mode the winner is whoever played most. It also
compounds: someone joining in month six can never catch a week-one player. A daily
board is cheap to compute, gives everyone a shot each morning, and makes today's
puzzle the thing people talk about.

---

## Phase 5 — UI redesign

Last, deliberately. The archive browser, daily board, quota states, and upgrade
flow are all new surfaces — redesigning before they exist means doing it twice.

---

## Anthology

Feasible, and **traffic is not the constraint.** Three games at 10k daily players
each is ~3 writes/sec. The marginal infrastructure cost of game two is near zero
because auth, leaderboards, caching, Stripe, and rate limiting are all shared.

What actually scales per game: **the data pipeline** (the expensive one) and **the
daily editorial burden** — three dailies is three chances every morning to ship
something broken. Mitigate by seeding puzzles 90 days ahead.

**Decision: build the schema multi-game now, ship game two only once Journeyman
has retention.** The schema costs one column and a `jsonb` today and a data
migration in a year. An anthology of one good game beats one of three thin ones.

When game two comes, reuse the NBA dataset already ingested — guess the player
from a stat line, from teammates, from a draft class. That makes it a weekend
rather than another month of pipeline work.

One account, one lifetime unlock across all games: each new game increases the
value of an unlock people already bought, so early buyers feel rewarded.

**Naming:** "Journeyman" doesn't extend to an anthology. Pick the umbrella name
before backlinks accumulate — cheap now, painful in a year.

---

## Database: staying on Supabase

Supabase *is* Postgres, so there's no lock-in to escape, and the load is small.
AWS would cost ~3–5× more (~$70–120/mo vs $25, with the NAT gateway alone at
$32/mo before any traffic) for weeks of plumbing that adds nothing a player sees.

Reconsider only at sustained >500 writes/sec, multi-region write locality, or a
compliance requirement.

**If migrating ever becomes necessary:** `pg_dump --no-owner --no-acl` → RDS moves
the whole `public` schema verbatim. The hard part is `auth.users`, which belongs
to Supabase's GoTrue. Take GoTrue with you (it's open source — password hashes and
user IDs survive, nobody notices) rather than moving to Cognito, which **cannot
import bcrypt hashes** and would force a password reset on every user. Cut over
with logical replication and flip DNS.

Doing Phase 0 makes this dramatically simpler, because the frontend stops talking
to the database directly.
