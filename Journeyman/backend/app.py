from auth import AuthError, user_id_from_headers
from config import load_config
from flask import Flask, jsonify, request
from generate_players import daily_player, randomPlayer, today_eastern, use_pool_source
from sessions import (
    GAME_SLUG,
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
from werkzeug.exceptions import HTTPException

app = Flask(__name__)


def _build_session_store():
    """Postgres when configured, in-memory otherwise.

    The in-memory fallback keeps `python app.py` and the test suite working with
    no setup. It is NOT viable in production: each serverless invocation gets its
    own empty dict, so /guess would not find what /start created. Deployments
    must set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.
    """
    config = load_config()
    if not config.use_database:
        return InMemorySessionStore()

    from supabase_store import SupabaseSessionStore

    return SupabaseSessionStore.from_config(config)


def _wire_player_pool(config):
    """Point player selection at the players table when there is one.

    Without this the game reads nba_players.json, which has no curation gate --
    a career flagged for review would still be served as a puzzle.
    """
    if not config.use_database:
        return None

    from players_repo import PlayersRepo, teams_of

    from supabase import create_client

    repo = PlayersRepo(create_client(config.supabase_url, config.supabase_service_key))

    def fetch():
        return [
            {"id": row["id"], "name": row["name"], "teams": teams_of(row)}
            for row in repo.active_pool()
        ]

    use_pool_source(fetch)
    return repo


session_store = _build_session_store()
config = load_config()
players_repo = _wire_player_pool(config)


def _build_puzzles_repo(config):
    if not config.use_database:
        return None

    from puzzles_repo import PuzzlesRepo

    from supabase import create_client

    return PuzzlesRepo(create_client(config.supabase_url, config.supabase_service_key))


puzzles_repo = _build_puzzles_repo(config)


def _current_user_id():
    """The signed-in player, or None for anonymous play.

    Read from a verified token rather than the request body. A body field would
    let any caller write results under someone else's account, which is the last
    place the API still trusted the client.
    """
    return user_id_from_headers(
        request.headers,
        jwks_url=config.jwks_url,
        secret=config.supabase_jwt_secret,
    )


@app.route("/")
def home():
    return "Welcome to Journeyman"


@app.route("/api/health")
def api_health():
    """Liveness plus the one configuration fact worth checking from outside.

    `session_store` reports which store the process actually built, not what the
    environment claims. The in-memory fallback is silent by design -- it keeps
    local development working with no setup -- which makes it easy to deploy with
    a missing variable and not notice until sessions start vanishing between
    requests. This is how you notice.

    It also makes one cheap query, because knowing a store was *built* is not
    the same as knowing it works: this endpoint reported "persistent": true
    while Postgres was unreachable, and again while the tables were missing
    because a migration had never been applied.

    Deliberately says nothing about which project, which keys, or why a check
    failed: this endpoint is public, and "working or not" is the most it should
    ever reveal. The detail goes to the server log.
    """
    uses_database = type(session_store).__name__ != "InMemorySessionStore"

    database_ok = True
    if uses_database:
        try:
            session_store.check_reachable()
        except Exception:
            app.logger.exception("health check could not reach the database")
            database_ok = False

    body = {
        "status": "ok" if database_ok else "degraded",
        "session_store": "database" if uses_database else "memory",
        "persistent": uses_database,
        "database_reachable": database_ok if uses_database else None,
    }

    # 503 so an uptime monitor treats this as down. Reporting 200 while the
    # database is unreachable is how an outage goes unnoticed.
    return jsonify(body), (200 if database_ok else 503)


# ---------------------------------------------------------------------------
# Session API
#
# The only way to play. The stateless /new-game, /daily-game and /check-guess
# endpoints are gone: they shipped the answer to the browser and graded a
# client-supplied answer against a client-supplied position, which is what made
# every score forgeable.
#
# No response below contains the answer while a game is in progress.
# ---------------------------------------------------------------------------


def _todays_puzzle(puzzle_date):
    """The scheduled puzzle for today, scheduling one only if none exists.

    Reading the row first is the point: once written, a day's puzzle is fixed.
    The hash fallback below is what the schedule replaced -- it stays so a gap in
    the calendar degrades to yesterday's behaviour instead of breaking the daily,
    but a scheduled row always wins.
    """
    if puzzles_repo is not None:
        row = puzzles_repo.get(puzzle_date)
        if row and row.get("payload"):
            payload = row["payload"]
            return payload["player_name"], payload["teams"], payload["player_id"]

    player_name, teams, player_id, _ = daily_player()

    # The session's composite foreign key requires the row to exist.
    session_store.ensure_puzzle(
        GAME_SLUG,
        puzzle_date,
        {"player_name": player_name, "player_id": player_id, "teams": teams},
    )
    return player_name, teams, player_id


def _session_error(exc, status):
    return jsonify({"error": str(exc)}), status


@app.errorhandler(Exception)
def _unhandled(exc):
    """Return JSON from the API rather than Flask's HTML error page.

    The client parses `error` out of the body; an HTML 500 gave players a bare
    "Something went wrong" with nothing in it to diagnose. The message stays
    generic on purpose -- the detail belongs in the server log, not in a
    response anyone can read.
    """
    if isinstance(exc, HTTPException):
        # 404, 405 and the like are already correct answers, not failures. They
        # are only reshaped into JSON for API callers; re-raising them here
        # turned every unknown path into a 500.
        if request.path.startswith("/api/"):
            return jsonify({"error": exc.description}), exc.code
        return exc

    if request.path.startswith("/api/"):
        app.logger.exception("unhandled error on %s", request.path)
        return jsonify({"error": "The server hit an unexpected problem."}), 500

    app.logger.exception("unhandled error on %s", request.path)
    raise exc


def _authorise(session):
    """Confirm the caller owns this session.

    A session belonging to an account may only be acted on by that account --
    otherwise a leaked or logged session id would let anyone else play out
    someone's daily and bank the score against their name.

    An anonymous session has no owner to check against, so possession of the id
    is the only credential there is. That is the cost of allowing play without
    an account, and it is bounded: the ids are random UUIDs, and an anonymous
    session writes no result anyone can claim.
    """
    if session.user_id is None:
        return None

    caller = _current_user_id()
    if caller != session.user_id:
        return jsonify({"error": "this game belongs to someone else"}), 403

    return None


@app.route("/api/game/start", methods=["POST"])
def api_game_start():
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "unlimited")
    hard_mode = bool(body.get("hard_mode", False))

    # Never body.get("user_id") -- see _current_user_id.
    try:
        user_id = _current_user_id()
    except AuthError as exc:
        return _session_error(exc, 401)

    puzzle_date = None
    if mode == "daily":
        puzzle_date = today_eastern().isoformat()
        player_name, teams, player_id = _todays_puzzle(puzzle_date)
    else:
        exclude = body.get("exclude") or []
        exclude_ids = {int(x) for x in exclude if str(x).strip().lstrip("-").isdigit()}
        player_name, teams, player_id = randomPlayer(exclude_ids=exclude_ids)

    try:
        session = start_session(
            session_store,
            mode=mode,
            player_name=player_name,
            player_id=player_id,
            teams=teams,
            user_id=user_id,
            puzzle_date=puzzle_date,
            hard_mode=hard_mode,
        )
    except SessionError as exc:
        return _session_error(exc, 409 if "already played" in str(exc) else 400)

    return jsonify(public_view(session)), 201


@app.route("/api/game/<session_id>", methods=["GET"])
def api_game_get(session_id):
    session = session_store.get(session_id)
    if session is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(session)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/guess", methods=["POST"])
def api_game_guess(session_id):
    existing = session_store.get(session_id)
    if existing is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(existing)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    try:
        session = submit_guess(
            session_store,
            session_id,
            position=body.get("position"),
            guess=body.get("guess"),
        )
    except SessionNotFound as exc:
        return _session_error(exc, 404)
    except (SessionError, ValueError) as exc:
        return _session_error(exc, 400)

    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/hint", methods=["POST"])
def api_game_hint(session_id):
    existing = session_store.get(session_id)
    if existing is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(existing)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    try:
        session = use_hint(session_store, session_id)
    except SessionNotFound as exc:
        return _session_error(exc, 404)
    except SessionError as exc:
        return _session_error(exc, 400)

    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/hard-mode", methods=["POST"])
def api_game_hard_mode(session_id):
    existing = session_store.get(session_id)
    if existing is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(existing)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    try:
        session = set_hard_mode(session_store, session_id, body.get("enabled", False))
    except SessionNotFound as exc:
        return _session_error(exc, 404)
    except SessionError as exc:
        return _session_error(exc, 400)

    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/abandon", methods=["POST"])
def api_game_abandon(session_id):
    existing = session_store.get(session_id)
    if existing is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(existing)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    try:
        session = abandon(session_store, session_id)
    except SessionNotFound as exc:
        return _session_error(exc, 404)

    return jsonify(public_view(session))


if __name__ == "__main__":
    app.run(debug=True)
