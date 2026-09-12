# Journeyman

An NBA career-path guessing game. You are given a player's name and must name
every club he turned out for, **in the order he played for them**.

Live at **[journeymannba.com](https://www.journeymannba.com)**.

React frontend, Flask API, Supabase (Postgres + Auth), deployed on Vercel.

---

## The game

A daily puzzle everyone shares, and an unlimited mode for playing more.

Each stop on the road is one club. If a player returned to a club later, it
appears again as a separate stop — the order is the puzzle, not the set.

### Reading a stop

Colour is reinforcement, not the message. Each result says itself three ways,
so it survives a colour-blind reader and a greyscale screenshot:

| | Mark | Rule | Costs |
|---|---|---|---|
| **Correct** | tick | double rule, the way a ledger closes a settled line | — |
| **Wrong stop** | dagger, the printer's mark for "belongs elsewhere" | dashed | 25 points |
| **Never played there** | cross | struck through | one of three lives |

Naming a club he really played for, one slot out, is **not** a wrong answer. It
costs points rather than a life, because knowing a club is better play than not
knowing it — but it is not free, or anyone who knew the clubs could permute them
risk-free and the order would stop mattering.

### Scoring

Starts at **1000**.

- **Time** — 30 seconds free, then 1 point a second, capped at **600**. The clock
  runs on the server and keeps running while you are away; what it can take is
  bounded, so a puzzle finished hours later is worth much less rather than
  nothing.
- **Wrong club** — 100 each, and three ends the game
- **Wrong stop** — 25 each
- **Hint** — 150. Unlocks after two wrong clubs and reveals each remaining
  stop's conference
- **Floor** — no win scores below 100
- **Hard mode** — one mistake ends it, and a win is multiplied by 1.5

### What costs money

The daily puzzle is **free forever and needs no account**. Beyond it, five
unlimited games a day are free.

**Full Access** is a one-time payment. It removes the daily cap and unlocks the
archive of past dailies. It is not a subscription and does not renew.

---

## Running it

```bash
pip install -r backend/requirements-dev.txt
supabase start                 # local Postgres + auth, in Docker
supabase db reset              # schema + seed
python backend/app.py          # API on :5000

cd frontend && npm install && npm start
```

The app runs without Supabase configured — it falls back to the bundled player
file and an in-memory session store, which is enough to play but loses every
game between requests.

### Tests

```bash
pytest                         # backend
ruff check . && ruff format .
cd frontend && npm test
python backend/smoke_test.py --url <deployment>
```

Integration tests run against the local Supabase stack and **skip when it is not
up** — which means CI skips them. A path exercised only against a fake is not
really tested; this project has been bitten by that twice.

---

## How it is built

The answer never leaves the server while a game is running. `/api/game/start`
returns how many stops there are, not what they are. Scoring happens server-side
against the server clock, results are written by the service role, and identity
comes from a verified token rather than a request body.

```
backend/
  app.py              routes
  sessions.py         the game engine -- the answer lives here
  scoring.py          scoring rules
  quota.py            the free allowance
  entitlements.py     what someone bought, provider-agnostic
  stripe_billing.py   the only file that knows what Stripe is
  payment_events.py   makes a webhook safe to receive twice
  archive.py          past dailies
  rate_limit.py       application-level limiting
  observability.py    structured logging, Sentry
  smoke_test.py       plays a real game against a deployment
supabase/migrations/  applied by CI on merge to main
docs/ROADMAP.md       the phased plan
docs/nba-data.md      where the player data comes from
```

`CLAUDE.md` carries the conventions and the gotchas that have already cost time.

---

## The data

Careers are built from a public-domain dataset derived from
Basketball-Reference — 2,582 careers, of which about 1,345 are used and about
771 are recognisable enough for a daily.

Season-granularity data cannot order a mid-season trade: both clubs sit against
the same season with nothing saying which came first. Careers that cannot be
ordered confidently are **held out of the rotation** rather than guessed at.

## Not affiliated with the NBA

An independent project, not affiliated with, endorsed by, or connected to the
National Basketball Association, its teams, or its players. Club and player
names are used to describe real careers. All trademarks belong to their owners;
no logos or likenesses are used.
