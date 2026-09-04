from auth import AuthError, user_id_from_headers
from config import load_config
from flask import Flask, jsonify, request
from game_logic import guess_check
from generate_players import daily_player, randomPlayer, today_eastern
from sessions import (
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


session_store = _build_session_store()
config = load_config()


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

    Deliberately says nothing about which project, which keys, or whether they
    are valid: this endpoint is public, and "configured or not" is the most it
    should ever reveal.
    """
    uses_database = type(session_store).__name__ != "InMemorySessionStore"

    return jsonify(
        {
            "status": "ok",
            "session_store": "database" if uses_database else "memory",
            "persistent": uses_database,
        }
    )


@app.route("/new-game")
def new_game():
    exclude_param = request.args.get("exclude", "")
    exclude_ids = set()
    if exclude_param:
        try:
            exclude_ids = {int(x) for x in exclude_param.split(",") if x.strip()}
        except ValueError:
            pass

    player_name, teams, player_id = randomPlayer(exclude_ids=exclude_ids)
    return jsonify(
        {
            "Player": player_name,
            "PlayerID": player_id,
            "Teams": teams,
            "Number of Teams": len(teams),
        }
    )


@app.route("/daily-game")
def daily_game():
    player_name, teams, player_id, day_num = daily_player()
    return jsonify(
        {
            "Player": player_name,
            "PlayerID": player_id,
            "Teams": teams,
            "Number of Teams": len(teams),
            "DayNumber": day_num,
        }
    )


@app.route("/check-guess", methods=["POST"])
def check_guess():
    player_data = request.json
    guess = player_data.get("guess")
    correct_teams = player_data.get("teams")
    position = player_data.get("position")

    try:
        result = guess_check(guess, correct_teams, position)
    except ValueError as exc:
        # Every field here comes from the request body, so malformed input is a
        # 400 rather than an unhandled 500.
        return jsonify({"error": str(exc)}), 400

    return jsonify({"result": result})


# ---------------------------------------------------------------------------
# Session API (Phase 0)
#
# These run alongside the legacy endpoints above rather than replacing them, so
# this branch is safe to ship: the frontend still uses the old ones until
# feat/session-frontend switches over, and chore/lock-down-writes deletes them.
#
# The difference that matters: no response below ever contains the answer while
# a game is in progress.
# ---------------------------------------------------------------------------


def _session_error(exc, status):
    return jsonify({"error": str(exc)}), status


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
        player_name, teams, player_id, _ = daily_player()
        puzzle_date = today_eastern().isoformat()
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
