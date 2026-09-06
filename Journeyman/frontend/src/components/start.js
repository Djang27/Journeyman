// The free allowance is shown here rather than only on refusal. A cap a player
// discovers by hitting it reads as a wall; one they can see counting down reads
// as the terms. Same rule, different feeling, and it costs one line of text.
//
// `quota` is null whenever it does not apply -- the daily, or a player who is
// not metered -- so absence and zero stay distinct.
function StartScreen({
    on_start_daily,
    on_start_unlimited,
    daily_done,
    day_number,
    quota = null,
    quota_gone = false,
}) {
    const remaining = quota?.remaining
    const out_of_games = quota_gone || remaining === 0

    return (
        <div className="start-screen">
            <div>
                <div className="logo-title">Journeyman</div>
                <div className="logo-subtitle">Trace the career</div>
            </div>
            <div className="road-preview"></div>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', maxWidth: '300px', lineHeight: 1.6 }}>
                A player's name. Guess every team they played for, in order.
            </p>
            <div className="start-mode-btns">
                <button
                    className={`start-btn daily-start-btn ${daily_done ? 'daily-done' : ''}`}
                    onClick={on_start_daily}
                    disabled={daily_done}
                >
                    {daily_done ? `Daily #${day_number} Complete ✓` : `Daily Journey #${day_number}`}
                </button>
                <button
                    className="start-btn unlimited-start-btn"
                    onClick={on_start_unlimited}
                    disabled={out_of_games}
                >
                    Unlimited
                </button>
            </div>

            {out_of_games ? (
                // Says what is still available, not just what is not. The daily
                // is free forever and is the reason to come back tomorrow.
                <p className="quota-note quota-note-empty">
                    That's today's free games. The daily puzzle is always free —
                    more unlimited games tomorrow.
                </p>
            ) : remaining != null ? (
                <p className="quota-note">
                    {remaining} free {remaining === 1 ? 'game' : 'games'} left today
                </p>
            ) : null}
        </div>
    )
}

export default StartScreen
