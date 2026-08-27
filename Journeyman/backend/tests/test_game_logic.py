"""Tests for guess grading.

These are characterisation tests: they pin down what the code does *today* so
that Phase 0's move to server-side validation can be proven not to change any
player-visible behaviour. Where today's behaviour is wrong, the test is marked
xfail with a note rather than deleted -- when the bug is fixed the marker is
removed and the test stands.
"""

import pytest
from game_logic import answer_variations, guess_check

# A player who went Cleveland -> Miami -> Cleveland. Repeated teams are a real
# and deliberate shape in the data, so they get their own cases below.
RETURN_CAREER = ["cleveland cavaliers", "miami heat", "cleveland cavaliers"]
SIMPLE_CAREER = ["boston celtics", "miami heat", "utah jazz"]


class TestAnswerVariations:
    def test_accepts_full_name_and_nickname(self):
        assert answer_variations("boston celtics") == {"boston celtics", "celtics"}

    def test_multiword_city_keeps_only_the_last_word_as_nickname(self):
        # "trail" is not accepted on its own -- only "blazers" and the full name.
        assert answer_variations("portland trail blazers") == {
            "portland trail blazers",
            "blazers",
        }

    def test_numeric_nickname(self):
        assert answer_variations("philadelphia 76ers") == {"philadelphia 76ers", "76ers"}


class TestGuessCheck:
    def test_full_name_in_correct_slot_is_green(self):
        assert guess_check("boston celtics", SIMPLE_CAREER, 0) == "green"

    def test_nickname_in_correct_slot_is_green(self):
        assert guess_check("celtics", SIMPLE_CAREER, 0) == "green"

    def test_right_team_wrong_slot_is_yellow(self):
        assert guess_check("celtics", SIMPLE_CAREER, 2) == "yellow"

    def test_team_not_in_career_is_gray(self):
        assert guess_check("lakers", SIMPLE_CAREER, 0) == "gray"

    def test_nonsense_guess_is_gray(self):
        assert guess_check("not a team", SIMPLE_CAREER, 1) == "gray"

    def test_repeated_team_is_green_in_each_slot_it_occupies(self):
        assert guess_check("cavaliers", RETURN_CAREER, 0) == "green"
        assert guess_check("cavaliers", RETURN_CAREER, 2) == "green"

    def test_repeated_team_is_yellow_in_the_slot_between(self):
        assert guess_check("cavaliers", RETURN_CAREER, 1) == "yellow"

    def test_ambiguous_nickname_matches_either_franchise(self):
        # "hornets" is shared by Charlotte and New Orleans. The grader accepts it
        # for both, which is lenient but consistent -- pinned here so a future
        # change to answer_variations has to be deliberate about it.
        career = ["charlotte hornets", "new orleans hornets"]
        assert guess_check("hornets", career, 0) == "green"
        assert guess_check("hornets", career, 1) == "green"


class TestGuessCheckHardening:
    """Cases that matter once `position` arrives from an untrusted client."""

    def test_empty_guess_is_gray(self):
        assert guess_check("", SIMPLE_CAREER, 0) == "gray"

    @pytest.mark.xfail(
        strict=True,
        reason="guess is never lowercased server-side; App.js does it before sending, "
        "so a direct API call with 'Celtics' grades as gray",
    )
    def test_guess_is_case_insensitive(self):
        assert guess_check("Celtics", SIMPLE_CAREER, 0) == "green"

    @pytest.mark.xfail(
        strict=True,
        reason="negative position silently indexes from the end, so -1 grades "
        "against the last team instead of being rejected",
    )
    def test_negative_position_is_rejected(self):
        with pytest.raises((IndexError, ValueError)):
            guess_check("jazz", SIMPLE_CAREER, -1)

    def test_position_past_the_end_raises(self):
        # Documents today's behaviour: an out-of-range position is a 500, not a
        # 400. Phase 0 should validate the bound and return a clean error.
        with pytest.raises(IndexError):
            guess_check("celtics", SIMPLE_CAREER, 99)

    def test_empty_career_raises(self):
        with pytest.raises(IndexError):
            guess_check("celtics", [], 0)
