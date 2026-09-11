"""How hard a career is to guess, and who is fit to be a daily.

Two things make a Journeyman puzzle hard, and they compound:

* **Not knowing the player.** If the name means nothing, no amount of thinking
  helps -- it stops being a puzzle and becomes a lookup.
* **Path length.** Every extra stint is another slot to get exactly right, and
  the game ends after three wrong guesses however many slots there are.

An obscure player with two teams is fair. A star with eight is a good puzzle.
An obscure player with eight is not a puzzle at all.

## On judging fame

Career points per game alone is a poor signal, and Dennis Rodman is the proof:
7.3 a game across 911 games, five championships and two All-Star selections. A
scoring average calls him obscure; anyone who watched basketball in the nineties
does not.

So three signals, strongest first:

* **All-Star selections.** The clearest evidence a name was famous at the time,
  and the one that rescues defensive and role players.
* **Career games.** Longevity is recognisability. A player nobody has heard of
  does not last a decade.
* **Points per game.** Still useful at the top, where scoring is what made a
  name, and it is all the older data offers.

Deliberately five coarse buckets rather than a score, so nobody mistakes it for
precision it does not have.
"""

from __future__ import annotations

# Points per game, as a stand-in for "would a fan recognise this name".
# Boundaries chosen from the shipped pool's distribution: its median is 8.1 and
# its 90th percentile is 17.5.
STAR_PPG = 16.0  # a name almost any fan knows
STARTER_PPG = 11.0  # a recognisable starter
ROTATION_PPG = 8.0  # a rotation regular
ROLE_PPG = 6.0  # a role player a keen fan might place

# Longevity, as games played. A career past a thousand games belongs to someone
# a fan will place; one under two hundred usually does not.
#
# The middle threshold was 400, which is about five seasons -- a journeyman, and
# the journeyman is this game's subject rather than its headliner. It let
# longevity alone carry a player all the way into the most recognisable tier on
# no other evidence: Terry Dehere averaged exactly 8.0 points over exactly 402
# games with no All-Star selection, cleared both boundaries by a hair, and came
# out rated as well known. Eight seasons is a career; five is a stint.
LONG_CAREER_GAMES = 800
SOLID_CAREER_GAMES = 600
BRIEF_CAREER_GAMES = 150

# Whether a low scorer has played enough to be worth serving at all. Separate
# from the fame threshold above and deliberately still 400: these decide
# different things, and quietly moving this one with the other would have
# dropped forty-five careers -- Scalabrine, Cardinal, Gadzuric -- out of the
# playable pool as a side effect of retuning what "well known" means.
PROMOTION_CAREER_GAMES = 400

SHORT_PATH = 3  # two or three stints: the path itself is not the obstacle
MEDIUM_PATH = 5

# Daily puzzles are the shop window and the share loop, and a player who feels
# impossible reads as a broken game rather than a hard one. Unlimited mode is
# where the deep cuts belong.
MAX_DAILY_DIFFICULTY = 3

# Below this a career is too obscure to be worth serving at all, and above the
# stint cap it stops being guessable.
MIN_PROMOTABLE_PPG = 5.0
MAX_PROMOTABLE_STINTS = 9


def fame_for(career_ppg, career_games=None, all_star_selections=0):
    """0 for a star, 4 for a name nobody will place.

    Public because it is the axis a player actually asks about. `difficulty_for`
    folds this together with path length, which is the right measure of how hard
    a puzzle is and the wrong one for choosing a pool: a famous player with seven
    clubs scores as difficult and is the single best kind of puzzle this game
    has. Selecting on the composite would throw exactly those away.
    """
    # An All-Star was, by definition, famous that season. Two or more is a name
    # that outlived the career.
    if all_star_selections >= 2:
        return 0
    if all_star_selections == 1:
        return 1

    ppg = career_ppg or 0.0
    scoring = (
        0
        if ppg >= STAR_PPG
        else 1
        if ppg >= STARTER_PPG
        else 2
        if ppg >= ROTATION_PPG
        else 3
        if ppg >= ROLE_PPG
        else 4
    )

    if career_games is None:
        return scoring

    # Longevity pulls a low scorer back toward recognisable, and a short career
    # pushes a decent average away from it.
    if career_games >= LONG_CAREER_GAMES:
        return max(0, scoring - 2)
    if career_games >= SOLID_CAREER_GAMES:
        return max(0, scoring - 1)
    if career_games < BRIEF_CAREER_GAMES:
        return min(4, scoring + 1)
    return scoring


def _path_cost(stint_count):
    """0 for a short career, 2 for a long one."""
    if stint_count <= SHORT_PATH:
        return 0
    if stint_count <= MEDIUM_PATH:
        return 1
    return 2


def difficulty_for(career_ppg, stint_count, career_games=None, all_star_selections=0):
    """A 1-5 tier. 1 is a household name with a short path, 5 is neither."""
    # Obscurity dominates: a name you do not know cannot be reasoned out, while a
    # long path at least rewards knowing the player. Hence the heavier weight.
    raw = (
        1 + fame_for(career_ppg, career_games, all_star_selections) + _path_cost(stint_count) * 0.5
    )
    return max(1, min(5, round(raw)))


def is_daily_eligible(difficulty):
    return difficulty is not None and difficulty <= MAX_DAILY_DIFFICULTY


def should_promote(career_ppg, stint_count, validation_status, career_games=None):
    """Whether a career belongs in the playable pool at all.

    A rule rather than a person, because hand-reviewing works at 200 players and
    not at several thousand. What still gets reviewed by hand is the *schedule*
    -- 365 dailies a year is readable, a pool is not.
    """
    if validation_status != "ok":
        return False
    # A career long enough to be recognisable clears the scoring floor on its
    # own -- otherwise every defensive specialist is excluded by construction.
    if (career_ppg or 0.0) < MIN_PROMOTABLE_PPG and (career_games or 0) < PROMOTION_CAREER_GAMES:
        return False
    distinct = stint_count if isinstance(stint_count, int) else 0
    return 2 <= distinct <= MAX_PROMOTABLE_STINTS


def describe(difficulty):
    """What a rating means, said in terms of the two things it is made of.

    "obscure" was wrong for anything the daily schedules: the fame floor
    guarantees a scheduled tier 4 is a known player with a long path, so the
    log was calling Chris Duhon obscure on the strength of his having played
    for five clubs. A rating is a pair -- how well known, how long the path --
    and collapsing it to one word lost the half that was doing the work.
    """
    return {
        1: "household name, short path",
        2: "well known",
        3: "recognisable, or a longer path",
        4: "a long path, or a lesser name",
        5: "hard to place, and long",
    }.get(difficulty, "unrated")


# How well known a pool is, as something a player chooses.
#
# The complaint this answers: a uniform draw over the promoted pool serves a
# name nobody knows more often than not, and an unrecognisable name is not a
# hard puzzle -- it is a lookup, and it reads as a broken game.
#
# Named by what you get rather than by a difficulty number, because "level 3"
# tells nobody anything and these are not a difficulty ladder. Path length is
# deliberately left free inside every one of them.
POOL_BIG_NAMES = "big_names"
POOL_MIXED = "mixed"
POOL_DEEP_CUTS = "deep_cuts"

DEFAULT_POOL = POOL_MIXED

# The most obscure a player may be and still appear. Cumulative, so a wider
# pool always contains everything a narrower one did -- somebody loosening the
# setting should see more, never different.
POOLS = {
    POOL_BIG_NAMES: 1,
    POOL_MIXED: 2,
    POOL_DEEP_CUTS: 4,
}

# Shown to the player. Kept here rather than in the frontend so the boundary and
# the promise about it cannot drift apart.
POOL_LABELS = {
    POOL_BIG_NAMES: ("Big names", "Stars and All-Stars. You will know almost all of them."),
    POOL_MIXED: ("Mixed", "Stars, starters and the better-known role players."),
    POOL_DEEP_CUTS: (
        "Deep cuts",
        "The whole register, including players only a devotee will place.",
    ),
}


def pool_choices():
    """Every pool, in order, as the frontend renders them."""
    return [
        {"id": name, "label": POOL_LABELS[name][0], "note": POOL_LABELS[name][1]}
        for name in (POOL_BIG_NAMES, POOL_MIXED, POOL_DEEP_CUTS)
    ]


def max_fame(pool):
    """The obscurity ceiling for a named pool, falling back to the default.

    An unknown name falls back rather than raising: this arrives from a request
    body, and a stale client asking for a pool that no longer exists should get
    a game rather than an error.
    """
    return POOLS.get(pool, POOLS[DEFAULT_POOL])


def in_pool(fame, pool):
    """Whether a player of this fame belongs in the chosen pool."""
    return fame is not None and fame <= max_fame(pool)


# The shape of a week.
#
# Every daily is the same puzzle for everybody, so it has to be fair before it
# is interesting -- but a calendar of uniformly easy puzzles is boring, and one
# of uniformly hard ones drives away the people who arrived on Monday. The
# crossword answer is a ramp: start the week gently, end it hard, and let people
# find the day that suits them.
#
# Two rules do the work, and they are separate on purpose:
#
#   * A floor on fame, applied every day of the week. A name nobody knows is not
#     a hard puzzle, it is a lookup, and no amount of "it is Saturday" makes that
#     fair. This is the rule that answers "the dailies are too niche".
#   * A target difficulty per weekday, which moves with the path length rather
#     than with obscurity -- so Saturday is a well-known player who turned out
#     for eight clubs, not an unknown one who turned out for two.
#
# The two together are why difficulty 5 can never be a daily: every rating of 5
# requires fame 3 or worse, so the fame floor excludes the whole tier without
# having to name it.
DAILY_MAX_FAME = 2

# Monday easiest, Saturday hardest, Sunday a shade back. Indexed by
# `date.weekday()`, where Monday is 0.
WEEKDAY_TARGET = {
    0: 1,  # Monday
    1: 2,  # Tuesday
    2: 2,  # Wednesday
    3: 3,  # Thursday
    4: 3,  # Friday
    5: 4,  # Saturday
    6: 3,  # Sunday
}

# How much worse than the target an over-famous pick is treated as being. Large
# enough that a player below the fame floor is never chosen while any eligible
# player remains, small enough that the calendar still fills if they run out --
# the scheduler's standing rule is that widening beats failing.
FAME_FLOOR_PENALTY = 100

# Careers that ended before this are preferred against, gently.
#
# Fame is measured from scoring, longevity and All-Star selections, all of which
# a 1960s journeyman can clear while being a name almost nobody alive can place
# -- Wilbur Holland and Leonard Gray rate as fit and are not. Roughly one day a
# week landed there, and on the daily that is everybody's day, not one player's.
#
# A tilt rather than a cutoff, and deliberately weighted below a tier mismatch:
# an exactly-right older career still beats a modern one from the wrong tier.
# The game is about careers, plenty of the good ones are old, and a calendar
# that began in 1990 would be a worse game as well as a less accurate one.
MODERN_ERA = 1990
OLD_ERA_PENALTY = 0.5


def daily_target(day):
    """The difficulty this weekday is aiming at."""
    return WEEKDAY_TARGET[day.weekday()]


def daily_fit(player, day):
    """How well a player suits a given date. Lower is better, 0 is exact.

    A ranking rather than a filter, so scarcity degrades gracefully: when
    Monday's tier runs dry the next-closest tier is chosen, rather than the
    calendar failing or silently reaching for whatever is left.
    """
    fame = player.get("fame")
    tier = player.get("difficulty")
    # An unrated player is treated as failing the fame floor rather than as a
    # star -- the direction that cannot put an unknown on the front page.
    penalty = 0 if fame is not None and fame <= DAILY_MAX_FAME else FAME_FLOOR_PENALTY
    if tier is None:
        return penalty + FAME_FLOOR_PENALTY
    last_season = player.get("last_season")
    if last_season is not None and last_season < MODERN_ERA:
        penalty += OLD_ERA_PENALTY
    return penalty + abs(tier - daily_target(day))


def rate(row):
    """Fame and difficulty for a players-table row, derived rather than read.

    `players.difficulty` is written at import, which means it is a snapshot of
    whatever the rules were on the day that import ran. Retuning those rules
    then leaves every stored value stale until somebody remembers to re-import
    -- and the failure is silent, because a stale tier is a perfectly valid
    tier. Deriving costs three comparisons and removes the whole class.

    The column stays for reporting and for a future hand override; nothing that
    chooses a puzzle reads it any more.
    """
    ppg = row.get("career_ppg") if "career_ppg" in row else row.get("ppg")
    games = row.get("career_games") if "career_games" in row else row.get("games")
    all_star = row.get("all_star_selections") or 0
    stints = row.get("stints") or []
    teams = row.get("teams") or [stint["team"] for stint in stints]
    fame = fame_for(ppg, games, all_star)
    return fame, difficulty_for(ppg, len(teams), games, all_star)


def week_shape():
    """The curve, for printing. Monday first."""
    names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    return [(names[i], WEEKDAY_TARGET[i]) for i in range(7)]
