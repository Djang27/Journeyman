from flask import Flask, jsonify, request
from game_logic import guess_check
from generate_players import daily_player, randomPlayer, today_eastern
from sessions import (
    InMemorySessionStore,
    SessionError,
    SessionNotFound,
    abandon,
    public_view,
    start_session,
    submit_guess,
    use_hint,
)

app = Flask(__name__)

# The store the session endpoints use. In-memory for now, which is correct for
# tests and local runs but NOT for production -- each serverless invocation gets
# its own empty dict, so /guess would not find what /start created. The
# Postgres-backed store replaces this before feat/session-frontend switches the
# browser over; the legacy endpoints below are still what the game runs on.
session_store = InMemorySessionStore()


@app.route("/")
def home():
    return "Welcome to Journeyman"


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


@app.route("/api/game/start", methods=["POST"])
def api_game_start():
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "unlimited")
    user_id = body.get("user_id")
    hard_mode = bool(body.get("hard_mode", False))

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
    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/guess", methods=["POST"])
def api_game_guess(session_id):
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
    try:
        session = use_hint(session_store, session_id)
    except SessionNotFound as exc:
        return _session_error(exc, 404)
    except SessionError as exc:
        return _session_error(exc, 400)

    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/abandon", methods=["POST"])
def api_game_abandon(session_id):
    try:
        session = abandon(session_store, session_id)
    except SessionNotFound as exc:
        return _session_error(exc, 404)

    return jsonify(public_view(session))


if __name__ == "__main__":
    app.run(debug=True)
