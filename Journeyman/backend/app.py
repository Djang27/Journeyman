from flask import Flask, jsonify, request
from generate_players import randomPlayer
from game_logic import guess_check

app = Flask(__name__)

@app.route("/")
def home():
    return "Welcome to Journeyman"

@app.route("/new-game")
def new_game():
    player_name, teams = randomPlayer()
    return jsonify ({
        "Player" : player_name,
        "Teams" : teams,
        "Number of Teams": len(teams)
    })

@app.route("/check-guess", methods = ["POST"])
def check_guess():
    player_data = request.json
    guess = player_data.get("guess")
    correct_teams = player_data.get("teams")
    position = player_data.get("position")

    result = guess_check(guess, correct_teams, position)

    return jsonify ({
        "result": result
    }) 


if __name__ == "__main__":
    app.run(debug = True)

