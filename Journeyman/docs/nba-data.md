# Player data: current state and the plan

Drives Phase 1 of `ROADMAP.md`. Everything here is about **where puzzle content
comes from**, which is currently the weakest part of the project.

---

## The reframe

The instinct is to treat this as a live-data problem, and it isn't. **A retired
player's team history is immutable.** An active player's changes only when they
are traded or signed — a few dozen times a week during the season, never in the
off-season.

So there is no reason to call an API during a user request, and no reason to call
one more than weekly. Once ingestion is a scheduled job writing to Postgres, the
rate-limiting problem stops existing. That is the whole fix; the rest of this
document is about sourcing quality.

---

## What we have today

`backend/nba_players.json` — 200 players, generated 2026-06-02, season 2025-26.
Built by `refresh_nba_players.py`, which:

1. Calls `stats.nba.com/stats/commonallplayers` for every player in NBA history.
2. Shuffles, then calls `playercareerstats` **once per player** with a 0.6s sleep.
3. Keeps a player if they have ≥2 distinct teams and ≥5.0 career PPG.
4. Stops at 200.

### Problems, in order of severity

**1. The source is unusable in production.** `stats.nba.com` is undocumented, has
no SLA, requires exact browser headers to respond at all, and blocks datacenter
IP ranges aggressively — AWS and Vercel egress addresses get 403s routinely. It
is fine as a laptop tool. It cannot be a scheduled cloud job.

**2. The access pattern invites blocking.** One request per player with a 0.6s
sleep is ~50 minutes of sustained traffic from one IP to reach ~5,000 players.
That is exactly the shape that gets an IP banned.

**3. The pool is arbitrary, not curated.** `≥2 teams, ≥5 PPG` is a blunt filter,
and it is the real reason the pool feels random. Nothing chose these 200 players.
There is no notion of difficulty, no way to exclude a player whose data is wrong,
no way to hand-pick a good launch-day puzzle.

**4. The daily puzzle is coupled to the pool size.** `daily_player()` is
`md5(date) % len(players)`, so **adding a single player reshuffles every future
daily** — including dates already announced. There is a test that proves this:
`test_selection_shifts_when_the_pool_grows`.

**5. Only 200 players.** At one daily puzzle each, that is under seven months
before repeats, and unlimited mode exhausts it far faster.

**6. No verification path.** If a player's team list is wrong, there is no way to
notice before players do, and no way to correct it without hand-editing JSON.

---

## What "a proper dataset" means here

Acceptance criteria, so the investigation has a finish line:

- [ ] **Coverage**: every player with ≥2 distinct franchises in NBA history, not a
      sample. Expect a few thousand candidates.
- [ ] **Correct team sequences**, in chronological order, with mid-season trades
      handled and `TOT` (two-team totals) rows excluded.
- [ ] **Correct franchise naming across relocations and renames** — Seattle
      SuperSonics vs OKC, Vancouver vs Memphis, New Jersey vs Brooklyn, Charlotte
      Hornets → Bobcats → Hornets, Washington Bullets vs Wizards. The existing
      `TEAM_NAMES_BY_ABBR` map handles most of this and is worth keeping.
- [ ] **Enough signal to rank difficulty** — career games, minutes, or PPG, so
      puzzles can be paced across a week.
- [ ] **Refreshable** without a full re-fetch: a delta job that asks only what
      changed.
- [ ] **Licensed for this use**, and re-derivable if the source disappears.

---

## Candidate sources

Confidence noted honestly — some of this needs verifying before committing.

### Kaggle NBA database dumps — *likely primary for backfill*

Full-history SQLite/CSV dumps including player and season-team tables, updated
periodically by their maintainers. Downloaded as a file, so **no rate limits and
no blocking**.

- **Verify**: which dump is current and actively maintained; whether season-team
  rows are complete back to the 1940s–50s; the licence terms; how stale the most
  recent season is.
- **Risk**: maintained by volunteers; a dump can go stale or vanish. Mitigated by
  committing a derived snapshot to the repo.

### balldontlie.io — *likely primary for in-season deltas*

A documented NBA API with real API keys, a free tier, and paid tiers around
$10–40/month. The value here is not the data volume but that **the rate limits are
published**, so a job can be planned against them instead of guessing.

- **Verify**: current pricing and free-tier limits; whether historical
  season-by-season team data is available or only recent seasons; response shape
  for a player's career.
- **Risk**: if it only covers recent seasons it cannot do the backfill — but for
  weekly deltas of active players, recent is all we need.

### stats.nba.com — *demoted to a local tool*

Keep `refresh_nba_players.py` for spot-checks and repairing individual players
from a laptop. Never schedule it, never call it from a request, never call it from
CI.

### Basketball-Reference — *reference only, do not scrape*

The most complete and accurate source, and the one to check answers against by
hand. Their terms restrict automated scraping and they rate-limit aggressively.
Use published dataset dumps rather than crawling them.

---

## How correctness scales

The obvious plan -- check the data by hand -- does not survive contact with the
numbers. A few thousand careers cannot be read by a person, and a source that is
95% right still leaves a hundred broken puzzles. So the question is not "how do
we verify the data" but "how do we make the amount needing human eyes small".

Four layers, implemented in `backend/validation.py`:

**1. Impossible (automatic reject).** Franchise renames impose a strict order:
Seattle must precede Oklahoma City, Vancouver must precede Memphis, New Jersey
before Brooklyn. A career violating that is wrong, provably, with no source to
compare against. Consecutive duplicate stints mean the collapse failed. These
have no false positives, so they can be rejected outright.

**2. Implausible (review queue).** Patterns rare in reality rather than
impossible. The important one is A/B/A/B alternation, which is the fingerprint
of a mid-season trade whose rows were interleaved rather than sequenced.

This layer earns its place. Run over the shipped 200-player pool it flagged
**seven careers, 3.5%** -- and among them Bob Lanier, Connie Hawkins and Dwight
Jones, all pre-1985, all with the same alternation:

    Bob Lanier      DET / MIL / DET / MIL          should be DET / MIL
    Connie Hawkins  PHX / LAL / PHX / LAL / ATL    should be PHX / LAL / ATL
    Dwight Jones    ATL / HOU / CHI / HOU / CHI / LAL

Not three unrelated mistakes: one systematic bug in how pre-1985 seasons are
ordered, surfacing three times. Found with no external source at all.

**3. Cross-source agreement (the ingestion job).** Pull each career from two
independent sources. Where they agree, accept. Where they disagree, queue for
review. This is what turns "is the source right?" into a question that answers
itself for the overwhelming majority of players.

**4. The curation gate.** Ingested players land `is_active_for_puzzles = false`.
Nothing reaches a player until it is promoted, so an error that survives every
layer above still cannot become a puzzle by accident.

Behind all of it, players themselves are the last check -- a "this looks wrong"
report on the results screen costs little and reaches exactly the puzzles that
are wrong. Worth building once there are players to report.

### What this needs from the data

**Seasons, not just team names.** The current `nba_players.json` records
`["seattle supersonics", "phoenix suns"]` with no years, which makes era
validation impossible: there is no way to check that a Seattle stint falls
before 2008. The `players` table must store a season range per stint. This is a
hard requirement on whichever source wins, and the current format cannot express
it.

---

## Choosing a source

Validation says whether data is self-consistent. It cannot say whether it is
*true* -- all three pre-1985 careers above are self-consistent under layer 1.
That is what the ground truth in `backend/tests/fixtures/ground_truth.json` is
for.

Eighteen careers, chosen for the failure modes a source actually has rather than
for fame: three separate relocations in one career, the Bobcats and New Orleans
Hornets eras, players who returned to a former team, and the longest careers in
the pool. `backend/ground_truth.py` scores any candidate against them and reports
*how* it failed -- reordered stints, a dropped return, a missing franchise --
because that is what separates an unusable source from one needing a small fix.

These eighteen are a **calibration set, not a verification method**. They are
checked by hand once, to prove the automated layers agree with reality. After
that the layers carry the thousands.

1. **Verify the eighteen** against Basketball-Reference and fill in
   `verified_teams`. Unverified entries are skipped, so this pays off from the
   first one.
2. **Score each candidate** with `score_source` and record the results here.
3. **Check licensing** for whichever wins.
4. **Measure the backfill**: how many players clear "two distinct franchises",
   and what the difficulty distribution looks like.
5. **Write the decision down here**, so it is not re-litigated.

---

## Source evaluation, 2026-09-04

Scored against the eighteen verified careers in
`backend/tests/fixtures/ground_truth.json`.

| Source | Score | Coverage | Verdict |
|---|---|---|---|
| `stats.nba.com` (what ships today) | **15/18** | 1946–present | Most accurate, and **unreachable** |
| FiveThirtyEight historical CSV | **8/18** | 1977–2020 | Free and era-correct, too narrow |
| balldontlie.io | not tested | 1996+ for player-season data | Needs an API key |
| Kaggle `nbadb` | not tested | 1946–present | Needs a Kaggle account |

### stats.nba.com is dead, not slow

Three attempts with 60-second timeouts and backoff, from a residential machine:
two timeouts and one `RemoteDisconnected`. "Run it from a laptop" is not a
workaround — it does not answer at all. Its 15/18 is the best score of anything
tested and is irrelevant while it cannot be reached.

### What the FiveThirtyEight failures showed

Only 8/18, but the breakdown matters more than the number:

* **6 were coverage**, not accuracy — Connie Hawkins predates 1977, and five
  modern careers are truncated at 2020.
* **3 were mid-season trades ordered wrongly** (Benjamin, Williams, Barnes).
* **1 lost a return stint** (Boykins).

Its team codes are genuinely era-correct — `WSB` distinct from `WAS`, `CHH` from
`CHA` — which is more than the shipped ingestion managed.

### The finding that constrains every source

**Season-granularity data cannot order a mid-season trade.** Both teams appear
against the same season with nothing recording which came first. Only game-level
data with dates resolves it.

`stats.nba.com` scored well because its rows *happen* to arrive chronologically,
not because it states the order — which is exactly why the shipped pool has Bob
Lanier as DET/MIL/DET/MIL when that assumption failed.

So every season-level source carries a floor of ordering errors on traded
seasons. `career_builder` narrows it by reading the neighbouring seasons, and
reports what it cannot resolve; the review queue is where the remainder goes.
A source that claims zero errors here is not being honest.

### Where this leaves it

No free, unauthenticated source is better than what already ships. The two
untested candidates both need an account, and **Kaggle `nbadb` is the strongest
of them**: MIT licensed, 1946–present, updated daily, and built *from*
`stats.nba.com` — so it should reproduce that 15/18 without the availability
problem. Its `nbadb init` path rebuilds from the live API and is therefore no use
here; only the Kaggle download avoids that.

Next step is an account and a scored run, not more searching.

---

## Target design

Independent of which source wins:

```sql
create table players (
  id                     bigint primary key,   -- stable external id
  name                   text not null,
  teams                  jsonb not null,       -- ordered team sequence
  career_ppg             numeric,
  career_games           integer,
  difficulty             smallint,             -- 1-5, hand-set or derived
  is_active_for_puzzles  boolean not null default false,
  notes                  text,
  source                 text not null,
  updated_at             timestamptz not null default now()
);

create table daily_puzzles (
  game_slug   text not null references games(slug),
  puzzle_date date not null,
  player_id   bigint not null references players(id),
  primary key (game_slug, puzzle_date)
);
```

Two decisions carry most of the value:

**Ingested players land `is_active_for_puzzles = false`.** Promotion is a
deliberate act, whether by hand or by a rule. The pipeline surfaces candidates; it
does not pick answers. Every puzzle game with a reputation curates its pool.

**Daily puzzles are scheduled rows, not a hash.** Seeded weeks ahead, this gives
no repeats, a hand-picked launch day, deliberate difficulty pacing, an answer that
cannot shift mid-day, and the archive to sell in Phase 3.

---

## Notes for whoever implements this

- **Repeated teams are intentional.** Cleveland → Miami → Cleveland is three cells
  across two franchises, and `guess_check` already grades it correctly (right team,
  wrong slot → yellow). Do not "fix" it into a distinct-teams list.
- **Ambiguous nicknames are accepted for either franchise.** "hornets" matches both
  Charlotte and New Orleans. Lenient but consistent, and pinned by a test.
- **Seed from the existing JSON first**, before the bulk import, so the database
  read path is proven separately from the ingestion.
- **Never let a test hit a live API.** Record fixtures. Otherwise CI fails whenever
  the source rate-limits.
- **Keep `nba_players.json` in the repo** as the degraded-mode fallback pool even
  after Postgres becomes the source of truth.
