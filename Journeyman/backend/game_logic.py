def answer_variations(team):
    aliases = {team.lower()}
    team_words = team.split()
    aliases.add(team_words[-1])
    return aliases


def guess_check(guess, correct_teams, position):
    """Grade one guess against a career.

    Returns "green" (right team, right slot), "yellow" (right team, wrong slot)
    or "gray". Raises ValueError on input that cannot be graded -- callers get
    `position` from the request body, so it is untrusted.
    """
    if not isinstance(guess, str):
        raise ValueError(f"guess must be a string, got {type(guess).__name__}")

    if not correct_teams:
        raise ValueError("correct_teams must not be empty")

    if not isinstance(position, int) or not 0 <= position < len(correct_teams):
        raise ValueError(f"position {position!r} is outside 0..{len(correct_teams) - 1}")

    # Normalised here rather than trusting the caller: App.js lowercases before
    # sending, but a direct API call is under no such obligation.
    normalised = guess.strip().lower()

    potential_answers = [answer_variations(team) for team in correct_teams]

    if normalised in potential_answers[position]:
        return "green"

    for answers in potential_answers:
        if normalised in answers:
            return "yellow"

    return "gray"
