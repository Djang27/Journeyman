"""Supabase-backed SessionStore.

Talks to PostgREST over HTTPS with the service role key rather than opening a
Postgres connection. That is deliberate: on Vercel every serverless invocation
is its own process, so direct connections multiply with traffic and exhaust the
database's connection limit exactly when the game gets popular. HTTP has no pool
to exhaust.

The service role key bypasses row level security, which is what lets this read
`puzzles` and `game_sessions` -- tables migration 0002 gives no policies at all,
so nothing else can.

Row mapping is split into free functions so it can be tested without a network
or a database. The class itself is exercised against the local Supabase stack in
tests/test_supabase_store.py, which skips when that stack is not running.
"""

from __future__ import annotations

from datetime import datetime

from sessions import Session, SessionError, SessionStore

TABLE = "game_sessions"
RESULTS_TABLE = "game_results"
PUZZLES_TABLE = "puzzles"

# Fields the database owns. Everything else the engine tracks lives in `state`,
# which keeps migration 0002's column list stable as the game gains features.
_COLUMNS = (
    "id",
    "game_slug",
    "user_id",
    "mode",
    "puzzle_date",
    "answer",
    "state",
    "status",
    "started_at",
    "finished_at",
)


def to_row(session: Session) -> dict:
    """Session -> the row shape migration 0002 defines."""
    return {
        "id": session.id,
        "game_slug": session.game_slug,
        "user_id": session.user_id,
        "mode": session.mode,
        "puzzle_date": session.puzzle_date,
        "answer": {
            "teams": session.answer,
            "player_name": session.player_name,
            "player_id": session.player_id,
        },
        "state": {
            "results": session.results,
            "guesses": session.guesses,
            "wrong_guesses": session.wrong_guesses,
            "hint_used": session.hint_used,
            "hard_mode": session.hard_mode,
            "score": session.score,
        },
        "status": session.status,
        "started_at": session.started_at.isoformat(),
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
    }


def from_row(row: dict) -> Session:
    """The row shape -> Session. Inverse of to_row."""
    answer = row.get("answer") or {}
    state = row.get("state") or {}

    return Session(
        id=str(row["id"]),
        game_slug=row["game_slug"],
        mode=row["mode"],
        answer=list(answer.get("teams", [])),
        player_name=answer.get("player_name", ""),
        player_id=answer.get("player_id", 0),
        user_id=row.get("user_id"),
        puzzle_date=_date_str(row.get("puzzle_date")),
        results=list(state.get("results", [])),
        guesses=list(state.get("guesses", [])),
        wrong_guesses=state.get("wrong_guesses", 0),
        hint_used=bool(state.get("hint_used", False)),
        hard_mode=bool(state.get("hard_mode", False)),
        status=row.get("status", "active"),
        started_at=_parse_timestamp(row["started_at"]),
        finished_at=_parse_timestamp(row.get("finished_at")),
        score=state.get("score"),
    )


def _date_str(value):
    if value is None:
        return None
    return value if isinstance(value, str) else value.isoformat()


def _parse_timestamp(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # PostgREST returns ISO 8601 with a trailing Z or an explicit offset.
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


class SupabaseSessionStore(SessionStore):
    def __init__(self, client):
        self._client = client

    @classmethod
    def from_config(cls, config):
        from supabase import create_client

        config.require_database()
        return cls(create_client(config.supabase_url, config.supabase_service_key))

    def _table(self):
        return self._client.table(TABLE)

    def create(self, session: Session) -> Session:
        try:
            response = self._table().insert(to_row(session)).execute()
        except Exception as exc:
            # The partial unique index from migration 0002 is what actually
            # enforces one daily per player -- not application code, which a
            # concurrent second request could race past.
            if _is_unique_violation(exc):
                raise SessionError("daily already played") from exc
            raise

        return from_row(response.data[0])

    def get(self, session_id: str) -> Session | None:
        response = self._table().select(",".join(_COLUMNS)).eq("id", session_id).limit(1).execute()
        if not response.data:
            return None
        return from_row(response.data[0])

    def update(self, session: Session) -> Session:
        row = to_row(session)
        # The primary key is not rewritten on update.
        row.pop("id")
        response = self._table().update(row).eq("id", session.id).execute()
        if not response.data:
            raise SessionError("session vanished while being updated")
        return from_row(response.data[0])

    def ensure_puzzle(self, game_slug: str, puzzle_date: str, payload: dict) -> None:
        self._client.table(PUZZLES_TABLE).upsert(
            {"game_slug": game_slug, "puzzle_date": puzzle_date, "payload": payload},
            on_conflict="game_slug,puzzle_date",
        ).execute()

    def record_result(self, session: Session) -> None:
        """Insert the permanent record the Stats and leaderboard views read.

        Written with the service role, which is the whole point: migration 0002
        leaves game_results readable by its owner but writable only by the
        server, so a score cannot be invented by the browser.
        """
        elapsed = (
            int((session.finished_at - session.started_at).total_seconds())
            if session.finished_at
            else 0
        )

        self._client.table(RESULTS_TABLE).insert(
            {
                "user_id": session.user_id,
                "game_slug": session.game_slug,
                "player_name": session.player_name,
                "result": "win" if session.status == "won" else "loss",
                "wrong_guesses": session.wrong_guesses,
                "num_teams": len(session.answer),
                "time_seconds": max(0, elapsed),
                "hint_used": session.hint_used,
                "hard_mode": session.hard_mode,
                "score": session.score or 0,
                "game_mode": session.mode,
            }
        ).execute()

    def find_daily(self, user_id: str, puzzle_date: str) -> Session | None:
        response = (
            self._table()
            .select(",".join(_COLUMNS))
            .eq("game_slug", "journeyman")
            .eq("user_id", user_id)
            .eq("puzzle_date", puzzle_date)
            .eq("mode", "daily")
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return from_row(response.data[0])


def _is_unique_violation(exc) -> bool:
    """Postgres 23505, surfaced through PostgREST's error payload."""
    code = getattr(exc, "code", None)
    if code == "23505":
        return True
    return "23505" in str(exc) or "duplicate key" in str(exc).lower()
