import TeamList from "./team_list"

function GameScreen({player, teams, guesses, results, on_guess_change, on_submit, has_won, on_play_again}) {
    return (
        <div>
            <h2>Player: {player}</h2>
            <TeamList 
            teams = {teams}
            guesses = {guesses}
            results = {results}
            on_guess_change = {on_guess_change}
            on_submit = {on_submit} 
            />
            {has_won && (
                <div>
                    <h2>You Win! </h2>
                    <button onClick = {on_play_again}>Play Again</button>
                </div>
            )}
        </div>
    )
}

export default GameScreen