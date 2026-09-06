"""Server-authoritative game sessions.

Phase 0's core. The answer lives here and in Postgres, never in a response body,
and every rule that decides a game -- what counts as a win, how many wrong
guesses end it, how long it took -- is applied on this side of the wire.

The store is an interface with two implementations. `InMemorySessionStore` backs
the tests, so the suite never needs a database and CI never touches Supabase.
The Postgres-backed one arrives in the next slice; the engine below does not
care which it is holding.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from game_logic import guess_check
from scoring import calculate_score
from teams import conference

MAX_WRONG_GUESSES = 3
GAME_SLUG = "journeyman"


class SessionError(Exception):
    """Invalid input or a rule violation. Callers turn this into a 4xx."""


class SessionNotFound(SessionError):
    pass


@dataclass(frozen=True)
class Session:
    """One game. `answer` and `player_name` never reach the client mid-game."""

    id: str
    game_slug: str
    mode: str
    answer: list[str]
    player_name: str
    player_id: int
    user_id: str | None = None
    puzzle_date: str | None = None
    results: list[str | None] = field(default_factory=list)
    guesses: list[str | None] = field(default_factory=list)
    wrong_guesses: int = 0
    misplaced_guesses: int = 0
    hint_used: bool = False
    hard_mode: bool = False
    status: str = "active"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    score: int | None = None

    @property
    def is_finished(self) -> bool:
        return self.status != "active"

    @property
    def has_won(self) -> bool:
        return bool(self.results) and all(r == "green" for r in self.results)


class SessionStore(ABC):
    """Persistence for sessions. Deliberately tiny: create, read, update."""

    @abstractmethod
    def create(self, session: Session) -> Session: ...

    @abstractmethod
    def get(self, session_id: str) -> Session | None: ...

    @abstractmethod
    def update(self, session: Session) -> Session: ...

    @abstractmethod
    def find_daily(self, user_id: str, puzzle_date: str) -> Session | None: ...

    @abstractmethod
    def check_reachable(self) -> None:
        """Raise if the store cannot actually be used right now.

        Distinct from "is a store configured": a process can hold a perfectly
        good client for a database that is down, or whose migrations were never
        applied. This is what makes /api/health mean something.
        """

    @abstractmethod
    def ensure_puzzle(self, game_slug: str, puzzle_date: str, payload: dict) -> None:
        """Make sure the day's puzzle row exists.

        A daily session carries a composite foreign key to `puzzles`, so the
        scheduled puzzle must exist before the session can. Today's puzzle is
        deterministic, so the server can write it on first use.

        This is a lazy scheduler standing in for a real one. Phase 1 seeds
        `puzzles` weeks ahead, which is what gives no repeats, a hand-picked
        launch day, and an archive; then this becomes a no-op safety net.
        """

    @abstractmethod
    def record_result(self, session: Session) -> None:
        """Write the finished game to game_results.

        Separate from the session row because the two have different lifetimes:
        a session is working state, a result is the permanent record the Stats,
        History and leaderboard views read. Until Phase 0 this insert was done
        by the browser, which is why a score could be invented.
        """


class InMemorySessionStore(SessionStore):
    """For tests and local runs without a database.

    Not usable in production: each serverless invocation would get its own empty
    dict, so a session created by /start would not exist by the time /guess ran.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self.recorded: list[Session] = []
        self.puzzles: dict[tuple[str, str], dict] = {}

    def create(self, session: Session) -> Session:
        if session.mode == "daily" and session.user_id:
            existing = self.find_daily(session.user_id, session.puzzle_date)
            if existing is not None:
                # Mirrors the partial unique index in migration 0002. The
                # database is the real guarantee; this keeps the fake honest.
                raise SessionError("daily already played")
        self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def update(self, session: Session) -> Session:
        self._sessions[session.id] = session
        return session

    def check_reachable(self) -> None:
        return None

    def ensure_puzzle(self, game_slug: str, puzzle_date: str, payload: dict) -> None:
        self.puzzles[(game_slug, puzzle_date)] = payload

    def record_result(self, session: Session) -> None:
        self.recorded.append(session)

    def find_daily(self, user_id: str, puzzle_date: str) -> Session | None:
        for session in self._sessions.values():
            if (
                session.mode == "daily"
                and session.user_id == user_id
                and session.puzzle_date == puzzle_date
            ):
                return session
        return None


def start_session(
    store: SessionStore,
    mode: str,
    player_name: str,
    player_id: int,
    teams: list[str],
    user_id: str | None = None,
    puzzle_date: str | None = None,
    hard_mode: bool = False,
    now: datetime | None = None,
) -> Session:
    if mode not in ("daily", "unlimited"):
        raise SessionError(f"unknown mode {mode!r}")
    if not teams:
        raise SessionError("a session needs at least one team")

    session = Session(
        id=str(uuid.uuid4()),
        game_slug=GAME_SLUG,
        mode=mode,
        answer=list(teams),
        player_name=player_name,
        player_id=player_id,
        user_id=user_id,
        puzzle_date=puzzle_date,
        results=[None] * len(teams),
        guesses=[None] * len(teams),
        hard_mode=hard_mode,
        started_at=now or datetime.now(UTC),
    )
    return store.create(session)


def resume_daily(
    store: SessionStore,
    user_id: str | None,
    puzzle_date: str | None,
) -> Session | None:
    """The unfinished daily this player already has, if any.

    A daily is one attempt per player, enforced by a unique index. That is the
    right rule and it is also a trap: the browser holds the session id in memory
    only, so a refresh mid-game used to leave the player locked out of a puzzle
    they had not finished, with no way back in. Handing the existing session
    back turns that from a lockout into a resume.

    Only *unfinished* sessions come back. A finished one still means "already
    played" -- resuming is not a second attempt.
    """
    if not user_id or not puzzle_date:
        # Anonymous play is not attributable, so there is nothing to resume and
        # nothing stopping a fresh start.
        return None
    existing = store.find_daily(user_id, puzzle_date)
    if existing is None or existing.is_finished:
        return None
    return existing


def submit_guess(
    store: SessionStore,
    session_id: str,
    position: int,
    guess: str,
    now: datetime | None = None,
) -> Session:
    """Grade one guess and persist the result. Finishes the game if it ended."""
    session = store.get(session_id)
    if session is None:
        raise SessionNotFound("no such session")
    if session.is_finished:
        raise SessionError("this game is already over")
    if not isinstance(position, int) or not 0 <= position < len(session.answer):
        raise SessionError(f"position {position!r} is outside 0..{len(session.answer) - 1}")
    if session.results[position] == "green":
        raise SessionError("that slot is already solved")

    # guess_check validates and normalises the guess itself.
    result = guess_check(guess, session.answer, position)

    results = list(session.results)
    guesses = list(session.guesses)
    results[position] = result
    guesses[position] = guess.strip().lower()

    wrong_guesses = session.wrong_guesses
    misplaced_guesses = session.misplaced_guesses

    if result == "yellow":
        # A misplacement is not a wrong answer: the team is right, the slot is
        # not. It costs no life, in hard mode either, because "one mistake ends
        # it" should mean a mistake. It costs points instead -- scoring.py --
        # so knowing the teams but not the order is not free.
        misplaced_guesses += 1
    elif result != "green":
        # Hard mode ends the game on the first genuine mistake.
        wrong_guesses = MAX_WRONG_GUESSES if session.hard_mode else wrong_guesses + 1

    updated = replace(
        session,
        results=results,
        guesses=guesses,
        wrong_guesses=wrong_guesses,
        misplaced_guesses=misplaced_guesses,
    )

    if updated.has_won:
        updated = _finish(updated, "won", now)
    elif wrong_guesses >= MAX_WRONG_GUESSES:
        updated = _finish(updated, "lost", now)

    stored = store.update(updated)
    _record_if_finished(store, stored)
    return stored


def use_hint(store: SessionStore, session_id: str) -> Session:
    session = store.get(session_id)
    if session is None:
        raise SessionNotFound("no such session")
    if session.is_finished:
        raise SessionError("this game is already over")
    if session.wrong_guesses < 2:
        # Matches the frontend gate: the hint unlocks after two wrong guesses.
        raise SessionError("the hint is not available yet")

    return store.update(replace(session, hint_used=True))


def set_hard_mode(store: SessionStore, session_id: str, enabled: bool) -> Session:
    """Toggle hard mode, only while the board is untouched.

    The player flips this after seeing who they have been given, so it cannot be
    settled at start time. Locking it to a blank board is what stops someone
    turning it on for the multiplier once they already know they are winning.
    """
    session = store.get(session_id)
    if session is None:
        raise SessionNotFound("no such session")
    if session.is_finished:
        raise SessionError("this game is already over")
    if any(result is not None for result in session.results):
        raise SessionError("hard mode is locked once the game has started")

    return store.update(replace(session, hard_mode=bool(enabled)))


def abandon(store: SessionStore, session_id: str, now: datetime | None = None) -> Session:
    session = store.get(session_id)
    if session is None:
        raise SessionNotFound("no such session")
    if session.is_finished:
        return session
    return store.update(_finish(session, "abandoned", now))


def _record_if_finished(store: SessionStore, session: Session) -> None:
    """Persist a won or lost game to game_results.

    Abandoned games are deliberately not recorded: walking away is not a result,
    and counting it as a loss would punish closing a tab.

    Anonymous games are not recorded either -- game_results.user_id is not
    nullable, and there is no account to attribute them to.
    """
    if session.status not in ("won", "lost") or session.user_id is None:
        return

    store.record_result(session)


def _finish(session: Session, status: str, now: datetime | None) -> Session:
    finished_at = now or datetime.now(UTC)
    elapsed = elapsed_seconds(session, finished_at)

    score = calculate_score(
        result="win" if status == "won" else "loss",
        time_seconds=elapsed,
        wrong_guesses=session.wrong_guesses,
        hint_used=session.hint_used,
        hard_mode=session.hard_mode,
        misplaced_guesses=session.misplaced_guesses,
    )

    return replace(session, status=status, finished_at=finished_at, score=score)


def elapsed_seconds(session: Session, now: datetime | None = None) -> int:
    """Elapsed time from the server clock, never the browser's."""
    end = session.finished_at or now or datetime.now(UTC)
    return max(0, int((end - session.started_at).total_seconds()))


def public_view(session: Session, now: datetime | None = None) -> dict:
    """What the client is allowed to see.

    `answer` is included only once the game is over, so the results screen can
    show the career. While a game is active it is absent -- that omission is the
    whole point of Phase 0.
    """
    view = {
        "session_id": session.id,
        "player": session.player_name,
        "mode": session.mode,
        "num_teams": len(session.answer),
        "results": session.results,
        "guesses": session.guesses,
        "wrong_guesses": session.wrong_guesses,
        "max_wrong_guesses": MAX_WRONG_GUESSES,
        # Shown in the score breakdown. Distinct from wrong_guesses because it
        # costs points rather than a life.
        "misplaced_guesses": session.misplaced_guesses,
        "hint_used": session.hint_used,
        "hard_mode": session.hard_mode,
        "status": session.status,
        "elapsed_seconds": elapsed_seconds(session, now),
    }

    # The hint reveals each unsolved slot's conference. Computed here so the
    # client never needs the answer to render it -- previously team_list.js
    # derived this from the teams array it had been handed.
    if session.hint_used:
        view["hints"] = [
            None if result == "green" else conference(team)
            for team, result in zip(session.answer, session.results, strict=True)
        ]

    if session.is_finished:
        view["teams"] = session.answer
        view["score"] = session.score
        view["player_id"] = session.player_id

    return view
