def guess_check(guess, correct_teams, position):
    if guess == correct_teams[position]:
        return "green"
    elif guess in correct_teams:
        return "yellow"
    else:
        return "gray"
    