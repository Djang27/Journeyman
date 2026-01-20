def answer_variations(team):
    aliases = {team.lower()}
    team_words = team.split()
    aliases.add(team_words[-1])
    return aliases

def guess_check(guess, correct_teams, position):

    potential_answers = [answer_variations(team) for team in correct_teams]

    if guess == correct_teams[position] or potential_answers[position]:
        return "green"
    elif guess in correct_teams or potential_answers:
        return "yellow"
    else:
        return "gray"
    