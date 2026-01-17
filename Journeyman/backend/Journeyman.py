from generate_players import randomPlayer
from game_logic import guess_check
def main():
    print("Welcome to JOURNEYMAN")
    print("Guess the teams that this player has played for!")

    player_name, correct_teams_list = randomPlayer()

    print (f"Player: {player_name} has played for {len(correct_teams_list)} teams")

    for i in range(len(correct_teams_list)):
        while True:
            guess = input(f"Team {i+1}: ").strip().lower()

            result = guess_check(guess, correct_teams_list, i)

            if result == "green":
                print("Correct!")
                break
            elif result == "yellow":
                print("Right Team, Incorrect Order, Please Try Again!")
            else:
                print("Never Played for this Team! Please Try Again")
    print("You Win!")
    print("Career path:")
    for team in correct_teams_list:
        print("→", team)
if __name__ == "__main__":
    main()

