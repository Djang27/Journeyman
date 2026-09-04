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
LONG_CAREER_GAMES = 800
SOLID_CAREER_GAMES = 400
BRIEF_CAREER_GAMES = 150

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


def _obscurity(career_ppg, career_games=None, all_star_selections=0):
    """0 for a star, 4 for a name nobody will place."""
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
        1
        + _obscurity(career_ppg, career_games, all_star_selections)
        + _path_cost(stint_count) * 0.5
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
    if (career_ppg or 0.0) < MIN_PROMOTABLE_PPG and (career_games or 0) < SOLID_CAREER_GAMES:
        return False
    distinct = stint_count if isinstance(stint_count, int) else 0
    return 2 <= distinct <= MAX_PROMOTABLE_STINTS


def describe(difficulty):
    return {
        1: "household name, short path",
        2: "well known",
        3: "recognisable, or a long path",
        4: "obscure",
        5: "obscure and long",
    }.get(difficulty, "unrated")
