import TeamList from "./team_list"

function GameScreen({ player, teams, guesses, results, on_guess_change, on_submit, has_won, has_lost, wrong_guesses, max_guesses, on_play_again, onInfo }) {
    const game_over = has_won || has_lost

    return (
        <div className="game-screen">
            <div className="player-header">
                <div className="player-header-top">
                    <div className="player-label">Today's Journeyman</div>
                    <button className="info-btn" onClick={onInfo} aria-label="How to play">?</button>
                </div>
                <div className="player-name">{player}</div>
            </div>

            <div className="lives-indicator">
                <span className="lives-label">Wrong Guesses</span>
                <div className="lives-dots">
                    {[...Array(max_guesses)].map((_, i) => (
                        <span key={i} className={`life-dot ${i < wrong_guesses ? 'used' : 'remaining'}`} />
                    ))}
                </div>
            </div>

            <TeamList
                teams={teams}
                guesses={guesses}
                results={results}
                on_guess_change={on_guess_change}
                on_submit={on_submit}
                game_over={game_over}
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

            {has_lost && (
                <div className="game-over-banner">
                    <div className="game-over-title">Journey Ended</div>
                    <p className="game-over-subtitle">{player}'s career path was:</p>
                    <ol className="correct-teams-list">
                        {teams.map((team, i) => (
                            <li key={i}>{team.replace(/\b\w/g, c => c.toUpperCase())}</li>
                        ))}
                    </ol>
                    <button className="play-again-btn game-over-btn" onClick={on_play_again}>
                        Try Again
                    </button>
                </div>
            )}
        </div>
    )
}

export default GameScreen
