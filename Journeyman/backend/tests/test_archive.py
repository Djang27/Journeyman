"""The archive: past dailies, for people who bought the game.

Two things here are worth more than the rest. A future date must never be
playable, because puzzles are scheduled about ninety days ahead and "playing the
archive" for next Tuesday would read out an answer nobody has seen. And the
listing must not name the player for a puzzle you have not played, because that
is the same answer in a place it is easy to forget about.
"""

from datetime import date

import pytest
from archive import (
    ArchiveError,
    check_playable,
    day_number,
    listing,
    playable_range,
)
from generate_players import LAUNCH_DATE

TODAY = date(2026, 9, 6)
YESTERDAY = date(2026, 9, 5)


def puzzle(name="Bob Lanier", teams=("Detroit Pistons", "Milwaukee Bucks")):
    return {"payload": {"player_name": name, "teams": list(teams), "player_id": "laniebo01"}}


class TestWhichDatesArePlayable:
    def test_yesterday_is_playable(self):
        assert check_playable(YESTERDAY.isoformat(), TODAY) == YESTERDAY

    def test_today_is_not(self):
        # Today's puzzle is the daily. Playing it through the archive would be
        # a second attempt at a one-attempt puzzle.
        with pytest.raises(ArchiveError):
            check_playable(TODAY.isoformat(), TODAY)

    def test_tomorrow_is_not(self):
        # The one that matters. Puzzles are scheduled ~90 days ahead, so this
        # would hand out an answer nobody has seen.
        with pytest.raises(ArchiveError, match="past"):
            check_playable(date(2026, 9, 7).isoformat(), TODAY)

    def test_a_date_months_ahead_is_not(self):
        with pytest.raises(ArchiveError, match="past"):
            check_playable(date(2026, 12, 1).isoformat(), TODAY)

    def test_before_launch_is_not(self):
        with pytest.raises(ArchiveError, match="launch"):
            check_playable(date(2026, 6, 10).isoformat(), TODAY)

    def test_launch_day_itself_is(self):
        assert check_playable(LAUNCH_DATE.isoformat(), TODAY) == LAUNCH_DATE

    @pytest.mark.parametrize(
        "bad",
        [None, "", "not-a-date", "2026-13-45", "2026/09/05", {}, ["2026-09-05"]],
    )
    def test_junk_is_refused_rather_than_guessed_at(self, bad):
        with pytest.raises(ArchiveError):
            check_playable(bad, TODAY)

    @pytest.mark.parametrize("compact", [20260905, "20260905"])
    def test_the_compact_iso_form_is_refused(self, compact):
        # date.fromisoformat has accepted "20260905" since Python 3.11, so this
        # parsed cleanly and the documented contract was not the enforced one.
        # Harmless -- the range check still applied -- but an API that accepts
        # shapes it does not document is one nobody can rely on.
        with pytest.raises(ArchiveError):
            check_playable(compact, TODAY)

    def test_the_range_ends_yesterday(self):
        earliest, latest = playable_range(TODAY)
        assert earliest == LAUNCH_DATE
        assert latest == YESTERDAY


class TestTheListingWithholdsAnswers:
    """A listing endpoint is an easy place to give away ninety answers."""

    def test_an_unplayed_puzzle_does_not_name_the_player(self):
        entries = listing({"2026-09-05": puzzle()}, played_dates=set(), today=TODAY)
        assert entries[0]["player"] is None

    def test_a_played_puzzle_does(self):
        # It is no longer an answer once you have finished it.
        entries = listing({"2026-09-05": puzzle()}, played_dates={"2026-09-05"}, today=TODAY)
        assert entries[0]["player"] == "Bob Lanier"

    def test_no_answer_leaks_through_any_field(self):
        # Asserted against the whole serialised entry rather than a named key,
        # so a future field carrying the answer is caught too.
        import json

        entries = listing({"2026-09-05": puzzle()}, played_dates=set(), today=TODAY)
        blob = json.dumps(entries).lower()
        assert "lanier" not in blob
        assert "pistons" not in blob
        assert "bucks" not in blob

    def test_the_number_of_teams_is_shown(self):
        # Not the answer, and it is what makes a row worth looking at.
        entries = listing({"2026-09-05": puzzle()}, played_dates=set(), today=TODAY)
        assert entries[0]["num_teams"] == 2


class TestTheListingItself:
    def test_future_puzzles_are_omitted(self):
        # The scheduler keeps ~90 days ahead in the same table.
        scheduled = {
            "2026-09-05": puzzle(),
            "2026-09-06": puzzle("Today"),
            "2026-10-01": puzzle("Future"),
        }
        entries = listing(scheduled, played_dates=set(), today=TODAY)
        assert [e["puzzle_date"] for e in entries] == ["2026-09-05"]

    def test_newest_first(self):
        scheduled = {d: puzzle() for d in ("2026-09-01", "2026-09-03", "2026-09-05")}
        entries = listing(scheduled, played_dates=set(), today=TODAY)
        assert [e["puzzle_date"] for e in entries] == ["2026-09-05", "2026-09-03", "2026-09-01"]

    def test_played_is_reported(self):
        scheduled = {"2026-09-05": puzzle(), "2026-09-04": puzzle()}
        entries = listing(scheduled, played_dates={"2026-09-04"}, today=TODAY)
        assert {e["puzzle_date"]: e["played"] for e in entries} == {
            "2026-09-05": False,
            "2026-09-04": True,
        }

    def test_the_limit_is_honoured(self):
        scheduled = {f"2026-08-{day:02d}": puzzle() for day in range(1, 31)}
        assert len(listing(scheduled, set(), TODAY, limit=5)) == 5

    def test_a_malformed_key_is_skipped_rather_than_raising(self):
        # The table is the source; a row that cannot be parsed should cost one
        # entry, not the whole listing.
        entries = listing({"not-a-date": puzzle(), "2026-09-05": puzzle()}, set(), TODAY)
        assert [e["puzzle_date"] for e in entries] == ["2026-09-05"]


class TestDayNumbers:
    def test_launch_day_is_one(self):
        assert day_number(LAUNCH_DATE) == 1

    def test_it_counts_from_launch(self):
        assert day_number(date(2026, 6, 12)) == 2
