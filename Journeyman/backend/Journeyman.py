from generate_players import randomPlayer

def main():
    print("Testing randomPlayer() function...\n")

    # Pick 5 random journeyman players
    for i in range(5):
        player_name, teams = randomPlayer()
        print(f"{i+1}. {player_name}")
        print(f"   Teams: {teams}\n")

if __name__ == "__main__":
    main()

