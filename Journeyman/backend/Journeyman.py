from generate_players import randomPlayer
from game_logic import guess_check
def main():
    print("Welcome to JOURNEYMAN")
    print("Guess the teams that this player has played for!")

    player_name, correct_teams_list = randomPlayer()

    print (f"Player: {player_name} has played for {len(correct_teams_list)} teams")

if __name__ == "__main__":
    main()

