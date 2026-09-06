"""Past dailies, for people who bought the game.

The half of the offer that is worth something. Removing a cap is a weak thing to
sell; ninety puzzles somebody actually wants to play is not.

## What the list may say

A date, a day number, and whether you have played it. Never the player's name
for a puzzle you have not played -- that is the answer, and putting it in a list
endpoint would give away every unplayed puzzle to anyone who called it. The same
rule as Phase 0, in a place it would be easy to forget: the answer does not go
on the wire before the game is over.

## Which dates are playable

Strictly the past, from launch to yesterday. The upper bound is the load-bearing
one. Puzzles are scheduled about ninety days ahead, so without it an owner could
"play the archive" for next Tuesday and read the answer to a puzzle nobody has
seen. That is not a paywall bug, it is an answer leak.
"""

from __future__ import annotations

from datetime import date, timedelta

# Matches generate_players.LAUNCH_DATE. Imported rather than duplicated at call
# time so the two cannot drift.
from generate_players import LAUNCH_DATE

MODE = "archive"


class ArchiveError(Exception):
    """The date cannot be played, and the message says why."""


def day_number(puzzle_date: date) -> int:
    """Which daily this was, counting from launch."""
    return (puzzle_date - LAUNCH_DATE).days + 1


def playable_range(today: date):
    """The window an archive puzzle may fall in: launch .. yesterday."""
    return LAUNCH_DATE, today - timedelta(days=1)


def parse_date(value) -> date:
    """Parse a requested date, strictly.

    Strictly, because date.fromisoformat has accepted the compact "20260905"
    form since Python 3.11, so str(value) on an integer parses cleanly. That is
    not dangerous -- the range check still applies -- but it means the contract
    this function advertises would not be the one it enforces, and an API that
    accepts shapes it does not document is one nobody can rely on.
    """
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value) != 10:
        raise ArchiveError("puzzle_date must be YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ArchiveError("puzzle_date must be YYYY-MM-DD") from exc


def check_playable(puzzle_date, today: date) -> date:
    """Validate a requested archive date, or say why not.

    Raises rather than returning a flag, because every caller here has to stop
    on failure and a boolean invites forgetting to.
    """
    parsed = parse_date(puzzle_date)
    earliest, latest = playable_range(today)

    if parsed > latest:
        # The one that matters. Puzzles are scheduled ~90 days ahead, so
        # allowing today or later would hand out unseen answers.
        raise ArchiveError("only past puzzles are in the archive")
    if parsed < earliest:
        raise ArchiveError("the archive starts at launch")

    return parsed


def listing(scheduled, played_dates, today: date, limit=60):
    """The archive as the client may see it: newest first, answers withheld.

    `scheduled` maps date-string -> puzzle row, `played_dates` is the set of
    dates this caller has already finished. The player's name appears only for
    a puzzle already played -- everything else would be the answer.
    """
    earliest, latest = playable_range(today)

    entries = []
    for date_string in sorted(scheduled, reverse=True):
        try:
            parsed = date.fromisoformat(date_string)
        except ValueError:
            continue
        if not (earliest <= parsed <= latest):
            continue

        played = date_string in played_dates
        payload = scheduled[date_string].get("payload") or {}

        entries.append(
            {
                "puzzle_date": date_string,
                "day_number": day_number(parsed),
                "played": played,
                # Only once it is no longer an answer.
                "player": payload.get("player_name") if played else None,
                "num_teams": len(payload.get("teams") or []) or None,
            }
        )
        if len(entries) >= limit:
            break

    return entries
