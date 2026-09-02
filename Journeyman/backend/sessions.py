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


class InMemorySessionStore(SessionStore):
    """For tests and local runs without a database.

    Not usable in production: each serverless invocation would get its own empty
    dict, so a session created by /start would not exist by the time /guess ran.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

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
    if result != "green":
        # Hard mode ends the game on the first mistake, matching App.js.
        wrong_guesses = MAX_WRONG_GUESSES if session.hard_mode else wrong_guesses + 1

    updated = replace(session, results=results, guesses=guesses, wrong_guesses=wrong_guesses)

    if updated.has_won:
        updated = _finish(updated, "won", now)
    elif wrong_guesses >= MAX_WRONG_GUESSES:
        updated = _finish(updated, "lost", now)

    return store.update(updated)


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


def abandon(store: SessionStore, session_id: str, now: datetime | None = None) -> Session:
    session = store.get(session_id)
    if session is None:
        raise SessionNotFound("no such session")
    if session.is_finished:
        return session
    return store.update(_finish(session, "abandoned", now))


def _finish(session: Session, status: str, now: datetime | None) -> Session:
    finished_at = now or datetime.now(UTC)
    elapsed = elapsed_seconds(session, finished_at)

    score = calculate_score(
        result="win" if status == "won" else "loss",
        time_seconds=elapsed,
        wrong_guesses=session.wrong_guesses,
        hint_used=session.hint_used,
        hard_mode=session.hard_mode,
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
        "hint_used": session.hint_used,
        "hard_mode": session.hard_mode,
        "status": session.status,
        "elapsed_seconds": elapsed_seconds(session, now),
    }

    if session.is_finished:
        view["teams"] = session.answer
        view["score"] = session.score
        view["player_id"] = session.player_id

    return view
