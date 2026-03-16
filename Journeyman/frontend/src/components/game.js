import TeamList from "./team_list"

function GameScreen({ player, teams, guesses, results, on_guess_change, on_submit, has_won, on_play_again }) {
    return (
        <div className="game-screen">
            <div className="player-header">
                <div className="player-label">Today's Journeyman</div>
                <div className="player-name">{player}</div>
            </div>

            <TeamList
                teams={teams}
                guesses={guesses}
                results={results}
                on_guess_change={on_guess_change}
                on_submit={on_submit}
            />

            {has_won && (
                <div className="win-banner">
                    <div className="win-title">Journey Complete</div>
                    <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
                        You traced {player}'s full career path.
                    </p>
                    <button className="play-again-btn" onClick={on_play_again}>
                        New Journey
                    </button>
                </div>
            )}
        </div>
    )
}

export default GameScreen