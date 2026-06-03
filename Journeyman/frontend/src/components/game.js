import TeamList from "./team_list"
import WinAnimation from "./WinAnimation"
import LoseAnimation from "./LoseAnimation"

function fmt_time(s) {
    const m   = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${String(sec).padStart(2, '0')}`
}

function GameScreen({ player, teams, guesses, results, on_guess_change, on_submit, has_won, has_lost, wrong_guesses, max_guesses, hint_active, on_hint, elapsed, final_time, on_play_again }) {
    const game_over      = has_won || has_lost
    const hint_available = wrong_guesses >= 2 && !hint_active && !game_over

    return (
        <div className="game-screen">
            <WinAnimation  active={has_won} />
            <LoseAnimation active={has_lost} />

            <div className="player-header">
                <div className="player-label">Today's Journeyman</div>
                <div className="player-name">{player}</div>
            </div>

            <div className="game-status-row">
                <div className="lives-indicator">
                    <span className="lives-label">Wrong Guesses</span>
                    <div className="lives-dots">
                        {[...Array(max_guesses)].map((_, i) => (
                            <span key={i} className={`life-dot ${i < wrong_guesses ? 'used' : 'remaining'}`} />
                        ))}
                    </div>
                </div>

                <div className={`game-timer ${game_over ? 'done' : ''}`}>
                    {fmt_time(game_over && final_time !== null ? final_time : elapsed)}
                </div>

                {hint_available && (
                    <button className="hint-btn" onClick={on_hint} title="Reveal which conference each team belongs to">
                        💡 Hint
                    </button>
                )}
                {hint_active && !game_over && (
                    <span className="hint-active-label">Conference hints on</span>
                )}
            </div>

            <TeamList
                teams={teams}
                guesses={guesses}
                results={results}
                on_guess_change={on_guess_change}
                on_submit={on_submit}
                game_over={game_over}
                hint_active={hint_active}
            />

            {has_won && (
                <div className="win-banner">
                    <div className="win-title">Journey Complete</div>
                    <p style={{ color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                        You traced {player}'s full career path.
                    </p>
                    {final_time !== null && (
                        <p className="result-time win">
                            Completed in {fmt_time(final_time)}
                        </p>
                    )}
                    <button className="play-again-btn" style={{ marginTop: '1.25rem' }} onClick={on_play_again}>
                        New Journey
                    </button>
                </div>
            )}

            {has_lost && (
                <div className="game-over-banner">
                    <div className="game-over-title">Journey Ended</div>
                    {final_time !== null && (
                        <p className="result-time loss">Time: {fmt_time(final_time)}</p>
                    )}
                    <p className="game-over-subtitle" style={{ marginTop: '0.75rem' }}>
                        {player}'s career path was:
                    </p>
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
