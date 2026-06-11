import { useState } from 'react'
import TeamList from "./team_list"
import WinAnimation from "./WinAnimation"
import LoseAnimation from "./LoseAnimation"
import { score_breakdown, SCORE_FLOOR, HARD_MULTIPLIER } from "../lib/scoring"

function fmt_time(s) {
    const m   = Math.floor(s / 60)
    const sec = s % 60
    return `${m}:${String(sec).padStart(2, '0')}`
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

    const [hard_flash, set_hard_flash] = useState(false)

    function handleHardModeToggle() {
        if (hard_mode_locked) return
        if (!hard_mode) {
            set_hard_flash(true)
            setTimeout(() => set_hard_flash(false), 800)
        }
        on_hard_mode_toggle()
    }

    return (
        <div className={`game-screen ${hard_flash ? 'hard-flash' : ''}`}>
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

                {!game_over && (
                    <div
                        className={`hard-mode-toggle ${hard_mode ? 'active' : ''} ${hard_mode_locked ? 'locked' : ''}`}
                        onClick={handleHardModeToggle}
                        title={hard_mode_locked ? 'Cannot change after guessing' : (hard_mode ? 'Hard mode on' : 'Activate hard mode')}
                        role="button"
                        aria-pressed={hard_mode}
                    >
                        <span className="hard-mode-toggle-label">Hard</span>
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

            {has_won && final_score !== null && (
                <div className="win-banner">
                    <div className="win-title">Journey Complete</div>
                    {hard_mode && <div className="hard-mode-badge">HARD MODE</div>}
                    <p style={{ color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                        You traced {player}'s full career path.
                    </p>
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
                    <button className="play-again-btn" style={{ marginTop: '1.5rem' }} onClick={on_play_again}>
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
                    <div className="score-display loss">
                        <span className="score-pts">0</span>
                        <span className="score-label">pts</span>
                    </div>
                    <p className="game-over-subtitle" style={{ marginTop: '1rem' }}>
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
