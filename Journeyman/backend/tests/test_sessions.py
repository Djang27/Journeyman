"""Session lifecycle, including the cases a hostile client would try.

Runs entirely against InMemorySessionStore, so the suite needs no database and
CI never touches Supabase.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sessions import (
    MAX_WRONG_GUESSES,
    InMemorySessionStore,
    SessionError,
    SessionNotFound,
    abandon,
    public_view,
    set_hard_mode,
    start_session,
    submit_guess,
    use_hint,
)

CAREER = ["boston celtics", "miami heat", "utah jazz"]
T0 = datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def store():
    return InMemorySessionStore()


def new_game(store, **kwargs):
    params = {
        "mode": "unlimited",
        "player_name": "Test Journeyman",
        "player_id": 1,
        "teams": CAREER,
        "now": T0,
    }
    params.update(kwargs)
    return start_session(store, **params)


class TestStart:
    def test_creates_an_active_session_with_a_blank_board(self, store):
        session = new_game(store)
        assert session.status == "active"
        assert session.results == [None, None, None]
        assert session.wrong_guesses == 0

    def test_rejects_an_unknown_mode(self, store):
        with pytest.raises(SessionError, match="unknown mode"):
            new_game(store, mode="freeplay")

    def test_rejects_an_empty_career(self, store):
        with pytest.raises(SessionError):
            new_game(store, teams=[])

    def test_a_second_daily_for_the_same_user_is_refused(self, store):
        new_game(store, mode="daily", user_id="u1", puzzle_date="2026-08-29")
        with pytest.raises(SessionError, match="daily already played"):
            new_game(store, mode="daily", user_id="u1", puzzle_date="2026-08-29")

    def test_the_next_day_is_a_new_daily(self, store):
        new_game(store, mode="daily", user_id="u1", puzzle_date="2026-08-29")
        assert new_game(store, mode="daily", user_id="u1", puzzle_date="2026-08-30")

    def test_unlimited_games_repeat_freely(self, store):
        for _ in range(5):
            assert new_game(store, mode="unlimited", user_id="u1")


class TestGuessing:
    def test_a_correct_guess_turns_the_slot_green(self, store):
        session = submit_guess(store, new_game(store).id, 0, "celtics")
        assert session.results[0] == "green"
        assert session.wrong_guesses == 0

    def test_a_misplaced_team_is_yellow_and_counts_as_wrong(self, store):
        session = submit_guess(store, new_game(store).id, 0, "jazz")
        assert session.results[0] == "yellow"
        assert session.wrong_guesses == 1

    def test_an_absent_team_is_gray_and_counts_as_wrong(self, store):
        session = submit_guess(store, new_game(store).id, 0, "lakers")
        assert session.results[0] == "gray"
        assert session.wrong_guesses == 1

    def test_casing_and_whitespace_do_not_matter(self, store):
        session = submit_guess(store, new_game(store).id, 0, "  CELTICS  ")
        assert session.results[0] == "green"

    def test_solving_every_slot_wins(self, store):
        sid = new_game(store).id
        for position, team in enumerate(CAREER):
            session = submit_guess(store, sid, position, team)
        assert session.status == "won"
        assert session.finished_at is not None

    def test_three_wrong_guesses_lose(self, store):
        sid = new_game(store).id
        for position in range(MAX_WRONG_GUESSES):
            session = submit_guess(store, sid, position, "lakers")
        assert session.status == "lost"
        assert session.score == 0

    def test_hard_mode_loses_on_the_first_mistake(self, store):
        sid = new_game(store, hard_mode=True).id
        session = submit_guess(store, sid, 0, "lakers")
        assert session.status == "lost"
        assert session.wrong_guesses == MAX_WRONG_GUESSES


class TestHostileInput:
    """Everything here arrives in a request body and must not be trusted."""

    def test_an_unknown_session_id_is_rejected(self, store):
        with pytest.raises(SessionNotFound):
            submit_guess(store, "not-a-session", 0, "celtics")

    def test_a_negative_position_is_rejected(self, store):
        with pytest.raises(SessionError, match="outside"):
            submit_guess(store, new_game(store).id, -1, "jazz")

    def test_a_position_past_the_end_is_rejected(self, store):
        with pytest.raises(SessionError, match="outside"):
            submit_guess(store, new_game(store).id, 99, "celtics")

    def test_a_non_integer_position_is_rejected(self, store):
        with pytest.raises(SessionError, match="outside"):
            submit_guess(store, new_game(store).id, "0", "celtics")

    def test_a_solved_slot_cannot_be_replayed(self, store):
        sid = new_game(store).id
        submit_guess(store, sid, 0, "celtics")
        with pytest.raises(SessionError, match="already solved"):
            submit_guess(store, sid, 0, "celtics")

    def test_a_finished_game_accepts_no_more_guesses(self, store):
        sid = new_game(store).id
        for position, team in enumerate(CAREER):
            submit_guess(store, sid, position, team)
        with pytest.raises(SessionError, match="already over"):
            submit_guess(store, sid, 0, "celtics")

    def test_a_lost_game_cannot_be_resumed(self, store):
        sid = new_game(store).id
        for position in range(MAX_WRONG_GUESSES):
            submit_guess(store, sid, position, "lakers")
        with pytest.raises(SessionError, match="already over"):
            submit_guess(store, sid, 2, "jazz")


class TestScoringAndTime:
    def test_elapsed_time_comes_from_the_server_clock(self, store):
        sid = new_game(store).id
        finished = submit_guess(store, sid, 0, "celtics", now=T0 + timedelta(seconds=45))
        submit_guess(store, sid, 1, "heat", now=T0 + timedelta(seconds=45))
        finished = submit_guess(store, sid, 2, "jazz", now=T0 + timedelta(seconds=45))

        assert finished.status == "won"
        # 45s elapsed, 15s past the 30s grace, so 1000 - 15.
        assert finished.score == 985

    def test_a_slow_win_is_floored_not_negative(self, store):
        sid = new_game(store).id
        late = T0 + timedelta(hours=2)
        for position, team in enumerate(CAREER):
            session = submit_guess(store, sid, position, team, now=late)
        assert session.score == 100

    def test_a_loss_scores_zero(self, store):
        sid = new_game(store).id
        for position in range(MAX_WRONG_GUESSES):
            session = submit_guess(store, sid, position, "lakers")
        assert session.score == 0


class TestHint:
    def test_is_locked_until_two_wrong_guesses(self, store):
        sid = new_game(store).id
        with pytest.raises(SessionError, match="not available"):
            use_hint(store, sid)

    def test_unlocks_after_two_wrong_guesses(self, store):
        sid = new_game(store).id
        submit_guess(store, sid, 0, "lakers")
        submit_guess(store, sid, 1, "lakers")
        assert use_hint(store, sid).hint_used is True

    def test_costs_points(self, store):
        sid = new_game(store).id
        submit_guess(store, sid, 0, "lakers", now=T0)
        submit_guess(store, sid, 1, "lakers", now=T0)
        use_hint(store, sid)
        # A wrong slot stays open -- only green locks -- so the player retries
        # both, then finishes. Two wrong guesses and the hint, inside the grace.
        submit_guess(store, sid, 0, "celtics", now=T0)
        submit_guess(store, sid, 1, "heat", now=T0)
        session = submit_guess(store, sid, 2, "jazz", now=T0)

        assert session.status == "won"
        assert session.score == 1000 - 200 - 150


class TestAbandon:
    def test_marks_the_session_abandoned(self, store):
        session = abandon(store, new_game(store).id)
        assert session.status == "abandoned"
        assert session.score == 0

    def test_is_idempotent(self, store):
        sid = new_game(store).id
        first = abandon(store, sid)
        assert abandon(store, sid).finished_at == first.finished_at


class TestPublicView:
    """The contract with the browser. This is where Phase 0 either holds or leaks."""

    def test_an_active_game_never_exposes_the_answer(self, store):
        view = public_view(new_game(store))
        assert "teams" not in view
        assert "score" not in view
        assert view["num_teams"] == len(CAREER)

    def test_the_answer_is_still_hidden_mid_game(self, store):
        sid = new_game(store).id
        submit_guess(store, sid, 0, "celtics")
        assert "teams" not in public_view(store.get(sid))

    def test_a_finished_game_reveals_the_answer(self, store):
        sid = new_game(store).id
        for position, team in enumerate(CAREER):
            session = submit_guess(store, sid, position, team)
        view = public_view(session)
        assert view["teams"] == CAREER
        assert view["status"] == "won"
        assert view["score"] > 0

    def test_no_serialised_field_leaks_a_team_name(self, store):
        sid = new_game(store).id
        submit_guess(store, sid, 0, "celtics")
        # "celtics" is a guess the player made, so it is legitimately echoed.
        # No *unguessed* team may appear anywhere in the payload.
        blob = repr(public_view(store.get(sid)))
        assert "miami heat" not in blob
        assert "utah jazz" not in blob


class TestHints:
    """The hint must not require the client to hold the answer."""

    def test_no_hints_before_one_is_used(self, store):
        assert "hints" not in public_view(new_game(store))

    def test_hints_give_the_conference_of_unsolved_slots(self, store):
        sid = new_game(store).id
        submit_guess(store, sid, 0, "lakers")
        submit_guess(store, sid, 1, "lakers")
        use_hint(store, sid)

        view = public_view(store.get(sid))
        # CAREER is celtics / heat / jazz -> East, East, West.
        assert view["hints"] == ["East", "East", "West"]

    def test_a_solved_slot_gets_no_hint(self, store):
        sid = new_game(store).id
        submit_guess(store, sid, 0, "celtics")
        submit_guess(store, sid, 1, "lakers")
        submit_guess(store, sid, 2, "lakers")
        use_hint(store, sid)

        assert public_view(store.get(sid))["hints"][0] is None

    def test_hints_never_name_a_team(self, store):
        sid = new_game(store).id
        submit_guess(store, sid, 0, "lakers")
        submit_guess(store, sid, 1, "lakers")
        use_hint(store, sid)

        blob = repr(public_view(store.get(sid))["hints"])
        for team in CAREER:
            assert team not in blob


class TestHardModeToggle:
    def test_can_be_turned_on_before_the_first_guess(self, store):
        sid = new_game(store).id
        assert set_hard_mode(store, sid, True).hard_mode is True

    def test_can_be_turned_off_again(self, store):
        sid = new_game(store, hard_mode=True).id
        assert set_hard_mode(store, sid, False).hard_mode is False

    def test_is_locked_once_a_guess_is_recorded(self, store):
        """Otherwise it could be switched on for the multiplier once winning."""
        sid = new_game(store).id
        submit_guess(store, sid, 0, "celtics")
        with pytest.raises(SessionError, match="locked"):
            set_hard_mode(store, sid, True)

    def test_is_locked_after_a_wrong_guess_too(self, store):
        sid = new_game(store).id
        submit_guess(store, sid, 0, "lakers")
        with pytest.raises(SessionError, match="locked"):
            set_hard_mode(store, sid, True)

    def test_cannot_be_changed_on_a_finished_game(self, store):
        sid = new_game(store).id
        abandon(store, sid)
        with pytest.raises(SessionError, match="already over"):
            set_hard_mode(store, sid, True)


class TestResultRecording:
    """Finished games become the permanent record Stats and the leaderboard read.

    Until Phase 0 the browser wrote this row, which is why a score could be
    invented. The server writes it now, from its own state.
    """

    def test_a_win_is_recorded(self, store):
        sid = new_game(store, user_id="u1").id
        for position, team in enumerate(CAREER):
            submit_guess(store, sid, position, team)

        assert len(store.recorded) == 1
        assert store.recorded[0].status == "won"

    def test_a_loss_is_recorded(self, store):
        sid = new_game(store, user_id="u1").id
        for position in range(MAX_WRONG_GUESSES):
            submit_guess(store, sid, position, "lakers")

        assert len(store.recorded) == 1
        assert store.recorded[0].status == "lost"

    def test_nothing_is_recorded_while_the_game_is_running(self, store):
        sid = new_game(store, user_id="u1").id
        submit_guess(store, sid, 0, "celtics")
        assert store.recorded == []

    def test_recorded_exactly_once(self, store):
        """A second write would double-count the game in every stat."""
        sid = new_game(store, user_id="u1").id
        for position, team in enumerate(CAREER):
            submit_guess(store, sid, position, team)

        with pytest.raises(SessionError):
            submit_guess(store, sid, 0, "celtics")

        assert len(store.recorded) == 1

    def test_anonymous_games_are_not_recorded(self, store):
        """game_results.user_id is not nullable and there is nobody to credit."""
        sid = new_game(store).id
        for position, team in enumerate(CAREER):
            submit_guess(store, sid, position, team)

        assert store.recorded == []

    def test_abandoning_records_nothing(self, store):
        """Walking away is not a loss; counting it would punish closing a tab."""
        sid = new_game(store, user_id="u1").id
        abandon(store, sid)
        assert store.recorded == []
