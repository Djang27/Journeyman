"""Reading and writing the players table.

The pool moves from backend/nba_players.json into Postgres here. The file stays
as a fallback for degraded mode, but it stops being the source of truth.

Careers are stored as stints carrying seasons; the game only needs the ordered
team names, so `teams_of` derives them. Keeping one representation rather than
two means they cannot disagree.
"""

from __future__ import annotations

from validation import validate

TABLE = "players"

# Everything the game and the review queue need. Listed rather than `*` so a
# column added later does not silently start crossing the wire.
COLUMNS = (
    "id",
    "name",
    "stints",
    "career_ppg",
    "career_games",
    "first_season",
    "last_season",
    "difficulty",
    "is_active_for_puzzles",
    "validation_status",
    "validation_notes",
    "source",
)


def teams_of(player):
    """The ordered franchise names, which is all the game itself needs."""
    return [stint["team"] for stint in player.get("stints") or []]


def stints_from_teams(teams, seasons=None):
    """Build stints from bare team names.

    `seasons` is optional because the legacy JSON has none -- those rows import
    with null seasons and are excluded from era validation until re-ingested
    from a source that provides them.
    """
    stints = []
    for index, team in enumerate(teams):
        stint = {"team": team, "from_season": None, "to_season": None}
        if seasons and index < len(seasons):
            stint["from_season"], stint["to_season"] = seasons[index]
        stints.append(stint)
    return stints


def to_row(player, source):
    """A player dict -> the row shape migration 0004 defines.

    Validation runs here rather than at read time, so the review queue is a
    query against a column instead of a script someone has to remember.
    """
    teams = player.get("teams") or teams_of(player)
    result = validate(teams)
    problems = result["impossible"] + result["implausible"]

    stints = player.get("stints") or stints_from_teams(teams)
    seasons = [s.get("from_season") for s in stints if s.get("from_season")]

    return {
        "id": player["id"],
        "name": player["name"],
        "stints": stints,
        "career_ppg": player.get("ppg"),
        "career_games": player.get("games"),
        "first_season": min(seasons) if seasons else None,
        "last_season": max(seasons) if seasons else None,
        "difficulty": player.get("difficulty"),
        "validation_status": result["verdict"],
        "validation_notes": "; ".join(problems) or None,
        "source": source,
        # Deliberately absent: is_active_for_puzzles. An import must never
        # promote a player into the puzzle rotation -- see migration 0004.
    }


class PlayersRepo:
    def __init__(self, client):
        self._client = client

    def _table(self):
        return self._client.table(TABLE)

    def upsert_many(self, players, source, batch_size=200):
        """Import or refresh players. Returns how many rows were written.

        Upsert on the primary key, so re-importing corrects rather than
        duplicates, and a player already promoted stays promoted.
        """
        rows = [to_row(player, source) for player in players]
        written = 0
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]
            self._table().upsert(batch, on_conflict="id").execute()
            written += len(batch)
        return written

    def active_pool(self):
        """Every player eligible for puzzles."""
        response = (
            self._table().select(",".join(COLUMNS)).eq("is_active_for_puzzles", True).execute()
        )
        return response.data or []

    def get(self, player_id):
        response = self._table().select(",".join(COLUMNS)).eq("id", player_id).limit(1).execute()
        return response.data[0] if response.data else None

    def needing_review(self, limit=100):
        """The review queue: what validation could not clear on its own."""
        response = (
            self._table()
            .select(",".join(COLUMNS))
            .in_("validation_status", ["review", "reject"])
            .limit(limit)
            .execute()
        )
        return response.data or []

    def set_active(self, player_id, active=True):
        """Promote or demote a player. The curation gate, as an operation."""
        self._table().update({"is_active_for_puzzles": active}).eq("id", player_id).execute()

    def counts(self):
        """Pool health at a glance: how many exist, how many are playable."""
        total = self._table().select("id", count="exact").limit(1).execute()
        active = (
            self._table()
            .select("id", count="exact")
            .eq("is_active_for_puzzles", True)
            .limit(1)
            .execute()
        )
        return {"total": total.count or 0, "active": active.count or 0}
