function StartScreen({ on_start_daily, on_start_unlimited, daily_done, day_number }) {
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
                <button className="start-btn unlimited-start-btn" onClick={on_start_unlimited}>
                    Unlimited
                </button>
            </div>
        </div>
    )
}

export default StartScreen
