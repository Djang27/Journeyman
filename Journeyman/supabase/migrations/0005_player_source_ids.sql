-- Player ids become text.
--
-- The pool moves to a Basketball-Reference derived source, whose player ids are
-- strings like "barnesc01" rather than the numeric ids stats.nba.com used.
-- External identifiers are strings in general, and hashing them into a bigint
-- to preserve this column would trade a correct type for a permanent lie about
-- what the value is.
--
-- Done now because it is cheap now: the table holds 200 fully re-importable
-- rows, and scheduled puzzles carry a denormalised payload, so nothing depends
-- on the id beyond provenance.

alter table public.puzzles
  drop constraint if exists puzzles_player_id_fkey;

alter table public.players
  alter column id type text using id::text;

alter table public.puzzles
  alter column player_id type text using player_id::text;

alter table public.puzzles
  add constraint puzzles_player_id_fkey
  foreign key (player_id) references public.players(id);

-- Which source a row came from, so a bad import can be identified and replaced
-- wholesale rather than merged into.
alter table public.players
  add column if not exists source_id text;

-- Fame signals the previous source did not provide. Career points per game
-- alone rates Dennis Rodman obscure -- 7.3 a game across 911 games and two
-- All-Star selections -- which is exactly the kind of player the daily wants.
alter table public.players
  add column if not exists all_star_selections smallint not null default 0;

alter table public.players
  add column if not exists seasons_played smallint;

comment on column public.players.id is
  'The source''s own identifier, e.g. a Basketball-Reference slug.';
comment on column public.players.all_star_selections is
  'Fame signal. Career scoring alone misjudges defensive and role players.';
