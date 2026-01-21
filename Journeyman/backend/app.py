from flask import Flask, jsonify, request
from generate_players import randomPlayer
from game_logic import guess_check

app = Flask(__name__)

@app.route("/")
def home():
    return("Journeyman")

@app.route("/new-game")
def new_game():
    player_name, teams = randomPlayer()
    return {
        "Player" : player_name,
        "Number of Teams": len(teams)
    }

if __name__ == "__main__":
    app.run(debug = True)

