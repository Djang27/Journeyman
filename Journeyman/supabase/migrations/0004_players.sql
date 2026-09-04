-- Phase 1: the player pool becomes data rather than a file.
--
-- backend/nba_players.json is 200 players, generated once, with no seasons and
-- no way to correct an error short of hand-editing JSON. This replaces it as the
-- source of truth; the file stays in the repo as a degraded-mode fallback.
--
-- Two things shape this table more than anything else:
--
--   * Stints carry SEASONS, not just team names. Without them era validation is
--     impossible -- there is no way to check a Seattle SuperSonics stint falls
--     before 2008, or that a Bobcats stint falls inside 2004-2014. The old
--     format could not express this, which is why a whole class of error went
--     undetected.
--
--   * Nothing is puzzle-eligible until promoted. `is_active_for_puzzles`
--     defaults to false, so an ingestion bug cannot become a puzzle by
--     accident. The pipeline surfaces candidates; a person picks answers.


create table if not exists public.players (
  -- The source's own id, kept so a re-import updates rather than duplicates.
  id                     bigint      primary key,
  name                   text        not null,

  -- Ordered career, one entry per stint:
  --   [{"team": "seattle supersonics", "from_season": 1995, "to_season": 1998}]
  --
  -- Seasons are the starting year, so 1995 means the 1995-96 season. A return to
  -- a former franchise is a separate entry, deliberately -- that repetition is
  -- the puzzle.
  stints                 jsonb       not null,

  career_ppg             numeric(4, 1),
  career_games           integer,
  first_season           smallint,
  last_season            smallint,

  -- 1-5, set by hand or derived. Lets a week of puzzles be paced rather than
  -- landing three impossible ones in a row.
  difficulty             smallint    check (difficulty between 1 and 5),

  -- The curation gate. See the note above.
  is_active_for_puzzles  boolean     not null default false,

  -- Output of backend/validation.py at import time, so the review queue is a
  -- query rather than a script someone has to remember to run.
  validation_status      text        not null default 'unreviewed'
                                     check (validation_status in
                                            ('unreviewed', 'ok', 'review', 'reject')),
  validation_notes       text,

  -- Which source this came from, so a bad one can be identified and re-imported.
  source                 text        not null,
  notes                  text,
  updated_at             timestamptz not null default now(),

  -- A career path needs somewhere to go.
  constraint players_stints_is_a_list check (jsonb_typeof(stints) = 'array'),
  constraint players_has_stints check (jsonb_array_length(stints) >= 1)
);

-- The hot query: draw a random eligible player for unlimited mode. Partial, so
-- it stays small however many candidates are ingested but not promoted.
create index if not exists players_active_for_puzzles
  on public.players (id)
  where is_active_for_puzzles;

-- The review queue.
create index if not exists players_needing_review
  on public.players (validation_status)
  where validation_status in ('review', 'reject');

-- Player data is not secret -- every finished game reveals a career -- but there
-- is no reason for a browser to be able to enumerate the pool, which would leak
-- future answers. Server only, like puzzles and sessions.
alter table public.players enable row level security;


-- Tie scheduled puzzles to the player they came from.
--
-- `puzzles.payload` stays: it is what the session reads, and denormalising it
-- means a puzzle already scheduled does not silently change if a player record
-- is later corrected. The reference is for provenance and for scheduling.
alter table public.puzzles
  add column if not exists player_id bigint references public.players(id);

create index if not exists puzzles_by_player on public.puzzles (game_slug, player_id);
