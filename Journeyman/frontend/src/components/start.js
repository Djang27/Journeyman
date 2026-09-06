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
    billing = null,
    buying = false,
    on_buy = null,
    on_open_archive = null,
}) {
    const remaining = quota?.remaining
    const out_of_games = quota_gone || remaining === 0

    // Offered only when the server says payments work, the player has not
    // already bought, and there is a reason to care. Someone with games left is
    // not being sold to mid-session.
    const can_buy = Boolean(billing?.available) && !billing?.owned && Boolean(on_buy)
    const offer_upgrade = can_buy && out_of_games

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

            {on_open_archive && (
                <button className="archive-link" onClick={on_open_archive}>
                    Browse the archive
                </button>
            )}

            {billing?.owned && (
                <p className="quota-note quota-note-owned">Unlimited access — thanks.</p>
            )}

            {out_of_games ? (
                // Says what is still available, not just what is not. The daily
                // is free forever and is the reason to come back tomorrow.
                <>
                    <p className="quota-note quota-note-empty">
                        That's today's free games. The daily puzzle is always free —
                        more unlimited games tomorrow.
                    </p>
                    {offer_upgrade && (
                        <button className="upgrade-btn" onClick={on_buy} disabled={buying}>
                            {buying ? 'Opening checkout…' : 'Unlock unlimited — one payment'}
                        </button>
                    )}
                </>
            ) : remaining != null ? (
                <p className="quota-note">
                    {remaining} free {remaining === 1 ? 'game' : 'games'} left today
                </p>
            ) : null}
        </div>
    )
}

export default StartScreen
