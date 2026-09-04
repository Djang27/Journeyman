"""How hard a career is to guess, and who is fit to be a daily.

Two things make a Journeyman puzzle hard, and they compound:

* **Not knowing the player.** If the name means nothing, no amount of thinking
  helps -- it stops being a puzzle and becomes a lookup.
* **Path length.** Every extra stint is another slot to get exactly right, and
  the game ends after three wrong guesses however many slots there are.

An obscure player with two teams is fair. A star with eight is a good puzzle.
An obscure player with eight is not a puzzle at all.

## On the fame proxy

Career points per game is the only recognisability signal the current data has,
and it is a poor one. It rates Alex English correctly and would rate Dennis
Rodman -- a genuinely famous journeyman -- as obscure, because he never scored.
It flatters high-usage players on bad teams.

Career games played is the better signal and is not in the data yet; seasons
would give era, which matters too. Both are noted in docs/nba-data.md as
requirements on whichever source replaces stats.nba.com. Until then this is
deliberately coarse: five buckets, not a score, so nobody mistakes it for
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


def _obscurity(career_ppg):
    """0 for a star, 4 for a name nobody will place."""
    ppg = career_ppg or 0.0
    if ppg >= STAR_PPG:
        return 0
    if ppg >= STARTER_PPG:
        return 1
    if ppg >= ROTATION_PPG:
        return 2
    if ppg >= ROLE_PPG:
        return 3
    return 4


def _path_cost(stint_count):
    """0 for a short career, 2 for a long one."""
    if stint_count <= SHORT_PATH:
        return 0
    if stint_count <= MEDIUM_PATH:
        return 1
    return 2


def difficulty_for(career_ppg, stint_count):
    """A 1-5 tier. 1 is a household name with a short path, 5 is neither."""
    # Obscurity dominates: a name you do not know cannot be reasoned out, while a
    # long path at least rewards knowing the player. Hence the heavier weight.
    raw = 1 + _obscurity(career_ppg) + _path_cost(stint_count) * 0.5
    return max(1, min(5, round(raw)))


def is_daily_eligible(difficulty):
    return difficulty is not None and difficulty <= MAX_DAILY_DIFFICULTY


def should_promote(career_ppg, stint_count, validation_status):
    """Whether a career belongs in the playable pool at all.

    A rule rather than a person, because hand-reviewing works at 200 players and
    not at several thousand. What still gets reviewed by hand is the *schedule*
    -- 365 dailies a year is readable, a pool is not.
    """
    if validation_status != "ok":
        return False
    if (career_ppg or 0.0) < MIN_PROMOTABLE_PPG:
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
