def answer_variations(team):
    aliases = {team.lower()}
    team_words = team.split()
    aliases.add(team_words[-1])
    return aliases

def guess_check(guess, correct_teams, position):

    potential_answers = [answer_variations(team) for team in correct_teams]

    if guess in potential_answers[position]:
        return "green"
    
    for answers in potential_answers:
        if guess in answers:
            return "yellow"
    
    return "gray"
     