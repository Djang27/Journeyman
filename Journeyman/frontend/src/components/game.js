import { useState, useEffect } from 'react'
import TeamList from "./team_list"
import WinAnimation from "./WinAnimation"
import LoseAnimation from "./LoseAnimation"
import { score_breakdown, SCORE_FLOOR, HARD_MULTIPLIER } from "../lib/scoring"

function toTitleCase(str) {
    if (!str) return ''
    return str.replace(/\b\w/g, c => c.toUpperCase())
}

function fmt_time(s) {
    const m   = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${String(sec).padStart(2, '0')}`
}

function CareerTimeline({ teams, guesses, results }) {
    return (
        <div className="career-timeline">
            {teams.map((team, i) => {
                const result    = results[i]
                const guess     = guesses[i]
                const isCorrect = result === 'green'
                const isClose   = result === 'yellow'
                const isWrong   = result === 'gray'

                let markerClass = 'ct-empty'
                if (isCorrect)     markerClass = 'ct-correct'
                else if (isClose)  markerClass = 'ct-close'
                else if (isWrong)  markerClass = 'ct-wrong'

                const showGuess = !isCorrect && guess && guess.trim()

                return (
                    <div key={i} className={`ct-stop ${markerClass}`}>
                        <div className={`ct-marker ${markerClass}`}>
                            {isCorrect ? '✓' : i + 1}
                        </div>
                        <div className="ct-content">
                            <span className="ct-team">{toTitleCase(team)}</span>
                            {showGuess && (
                                <span className="ct-guess">{toTitleCase(guess)}</span>
                            )}
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

function ScoreBreakdown({ final_time, wrong_guesses, hint_active, hard_mode }) {
    const { base, time_pen, hint_pen, wrong_pen } = score_breakdown({
        time_seconds: final_time,
        wrong_guesses,
        hint_used: hint_active,
        hard_mode,
    })
    const floored = (base - time_pen - hint_pen - wrong_pen) < SCORE_FLOOR

    return (
        <div className="score-breakdown">
            <span className="sb-item base">+{base}</span>
            {time_pen  > 0 && <span className="sb-item pen">−{time_pen} time</span>}
            {hint_pen  > 0 && <span className="sb-item pen">−{hint_pen} hint</span>}
            {wrong_pen > 0 && <span className="sb-item pen">−{wrong_pen} wrong</span>}
            {floored        && <span className="sb-item floor">(floor {SCORE_FLOOR})</span>}
            {hard_mode      && <span className="sb-item hard">×{HARD_MULTIPLIER} hard</span>}
        </div>
    )
}

function GameScreen({ player, teams, guesses, results, on_guess_change, on_submit, on_clear, has_won, has_lost, wrong_guesses, max_guesses, hint_active, on_hint, hard_mode, on_hard_mode_toggle, elapsed, final_time, final_score, on_play_again }) {
    const game_over        = has_won || has_lost
    const hint_available   = wrong_guesses >= 2 && !hint_active && !game_over
    const hard_mode_locked = results.some(r => r !== null) || game_over

    const [hard_flash,    set_hard_flash]    = useState(false)
    const [show_results,  set_show_results]  = useState(false)

    useEffect(() => {
        if (game_over) set_show_results(true)
    }, [game_over])

    function handleHardModeToggle() {
        if (hard_mode_locked) return
        if (!hard_mode) {
            set_hard_flash(true)
            setTimeout(() => set_hard_flash(false), 1500)
        }
        on_hard_mode_toggle()
    }

    return (
        <div className={`game-screen ${hard_flash ? 'hard-flash' : ''}`}>
            <WinAnimation  active={has_won && show_results} />
            <LoseAnimation active={has_lost} />

            <div className="player-header">
                <div className="player-label">Today's Journeyman</div>
                <div className="player-name">{player}</div>
            </div>

            <div className="game-status-row">
                <div className="lives-indicator">
                    <span className="lives-label">Wrong Guesses</span>
                    <div className="lives-dots">
                        {[...Array(hard_mode ? 1 : max_guesses)].map((_, i) => (
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

                {!game_over && (
                    <div
                        className={`hard-mode-toggle ${hard_mode ? 'active' : ''} ${hard_mode_locked ? 'locked' : ''}`}
                        onClick={handleHardModeToggle}
                        title={hard_mode_locked ? 'Cannot change after guessing' : (hard_mode ? 'Hard mode on' : 'Activate hard mode')}
                        role="button"
                        aria-pressed={hard_mode}
                    >
                        <span className="hard-mode-toggle-label">Hard Mode</span>
                        <div className="hard-mode-switch">
                            <div className="hard-mode-knob" />
                        </div>
                    </div>
                )}
            </div>

            <TeamList
                teams={teams}
                guesses={guesses}
                results={results}
                on_guess_change={on_guess_change}
                on_submit={on_submit}
                on_clear={on_clear}
                game_over={game_over}
                hint_active={hint_active}
            />

            {/* Re-open bar — shown when modal is dismissed */}
            {game_over && !show_results && (
                <div className="see-results-bar">
                    <button className="see-results-btn" onClick={() => set_show_results(true)}>
                        See Results
                    </button>
                    <button className="play-again-btn secondary-play-btn" onClick={on_play_again}>
                        {has_won ? 'New Journey' : 'Try Again'}
                    </button>
                </div>
            )}

            {/* Results modal overlay */}
            {game_over && show_results && (
                <div className="results-overlay" onClick={() => set_show_results(false)}>
                    <div className="results-modal" onClick={e => e.stopPropagation()}>
                        <button
                            className="results-close-btn"
                            onClick={() => set_show_results(false)}
                            aria-label="Close results"
                        >
                            ✕
                        </button>

                        {has_won && final_score !== null && (
                            <>
                                <div className="win-title">Journey Complete</div>
                                {hard_mode && <div className="hard-mode-badge">HARD MODE</div>}
                                {final_time !== null && (
                                    <p className="result-time win">Completed in {fmt_time(final_time)}</p>
                                )}
                                <div className="score-display win">
                                    <span className="score-pts">{final_score.toLocaleString()}</span>
                                    <span className="score-label">pts</span>
                                </div>
                                <ScoreBreakdown
                                    final_time={final_time}
                                    wrong_guesses={wrong_guesses}
                                    hint_active={hint_active}
                                    hard_mode={hard_mode}
                                />
                                <div className="ct-section-label">Career Path</div>
                                <CareerTimeline
                                    teams={teams}
                                    guesses={guesses}
                                    results={results}
                                />
                                <div className="results-modal-actions">
                                    <button className="results-review-btn" onClick={() => set_show_results(false)}>
                                        Review Guesses
                                    </button>
                                    <button className="play-again-btn" onClick={on_play_again}>
                                        New Journey
                                    </button>
                                </div>
                            </>
                        )}

                        {has_lost && (
                            <>
                                <div className="game-over-title">Journey Ended</div>
                                {final_time !== null && (
                                    <p className="result-time loss">Time: {fmt_time(final_time)}</p>
                                )}
                                <div className="ct-section-label" style={{ marginTop: '1rem' }}>
                                    {player}'s Career Path
                                </div>
                                <CareerTimeline
                                    teams={teams}
                                    guesses={guesses}
                                    results={results}
                                />
                                <div className="results-modal-actions">
                                    <button className="results-review-btn" onClick={() => set_show_results(false)}>
                                        Review Guesses
                                    </button>
                                    <button className="play-again-btn game-over-btn" onClick={on_play_again}>
                                        Try Again
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    )
}

export default GameScreen
