from flask import Flask, jsonify, request
from game_logic import guess_check
from generate_players import daily_player, randomPlayer

app = Flask(__name__)


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


if __name__ == "__main__":
    app.run(debug=True)
