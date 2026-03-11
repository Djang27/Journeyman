import TeamList from "./team_list"

function GameScreen({player, teams, guesses, results, on_guess_change, on_submit}) {
    return (
        <div>
            <h2>Player: {player}</h2>
            <TeamList 
            teams = {teams}
            guesses = {guesses}
            results = {results}
            on_guess_change = {on_guess_change}
            on_submit = {on_submit} />
        </div>
    )
}

export default GameScreen