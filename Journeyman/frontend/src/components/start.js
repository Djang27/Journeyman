function StartScreen({ onStart }) {
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
            <button className="start-btn" onClick={onStart}>
                Start Game
            </button>
        </div>
    )
}

export default StartScreen
