import { useState } from 'react'

const TABS = [
    { id: 'howto',   label: 'How to Play' },
    { id: 'account', label: 'Account' },
    { id: 'history', label: 'History' },
]

/* ── HOW TO PLAY ─────────────────────────────────────── */
function HowToPlayTab() {
    return (
        <div className="sidebar-tab-content">
            <div className="info-section">
                <p className="info-lead">
                    You're given an NBA player's name. Guess every team they played for, in the correct order, to complete their journey.
                </p>
            </div>

            <div className="info-section">
                <span className="info-heading">Each Stop = One Team</span>
                <p className="info-body">Each numbered stop on the road is one team in the player's career. Fill them all correctly to win.</p>
                <div className="info-roadmap">
                    <div className="info-mini-spine" />
                    <div className="info-road-stop">
                        <div className="info-marker correct">1</div>
                        <div className="info-card-mini correct">
                            <span>Los Angeles Lakers</span>
                            <span className="info-badge correct">✓ Correct stop</span>
                        </div>
                    </div>
                    <div className="info-road-stop">
                        <div className="info-marker close">2</div>
                        <div className="info-card-mini close">
                            <span>Chicago Bulls</span>
                            <span className="info-badge close">↔ Wrong stop</span>
                        </div>
                    </div>
                    <div className="info-road-stop">
                        <div className="info-marker wrong">3</div>
                        <div className="info-card-mini wrong">
                            <span>Boston Celtics</span>
                            <span className="info-badge wrong">✗ Not in career</span>
                        </div>
                    </div>
                </div>
            </div>

            <div className="info-section">
                <span className="info-heading">Color Feedback</span>
                <div className="info-legend">
                    <div className="info-legend-row">
                        <span className="info-dot correct" />
                        <div className="info-legend-text"><strong>Green</strong> — Right team at the right stop. Locked in!</div>
                    </div>
                    <div className="info-legend-row">
                        <span className="info-dot close" />
                        <div className="info-legend-text"><strong>Yellow</strong> — This team is in the career, but at a different stop.</div>
                    </div>
                    <div className="info-legend-row">
                        <span className="info-dot wrong" />
                        <div className="info-legend-text"><strong>Red</strong> — This team is not in the player's career at all.</div>
                    </div>
                </div>
            </div>

            <div className="info-section">
                <span className="info-heading">Lives</span>
                <div className="info-lives-row">
                    <span className="life-dot remaining" />
                    <span className="life-dot remaining" />
                    <span className="life-dot remaining" />
                    <span className="info-lives-label">3 chances</span>
                </div>
                <p className="info-body">
                    Only <strong>red</strong> guesses cost a life. Yellow is free — use it as a clue. Lose all 3 and the correct career path is revealed.
                </p>
            </div>

            <div className="info-section">
                <span className="info-heading">Tips</span>
                <ul className="info-tips">
                    <li>Type a city <em>("Los Angeles")</em> or nickname <em>("Lakers")</em> to search</li>
                    <li>Yellow clues tell you the team exists — just at a different stop</li>
                    <li>Arrow keys navigate suggestions, Enter to select</li>
                </ul>
            </div>
        </div>
    )
}

/* ── ACCOUNT ─────────────────────────────────────────── */
function AccountTab() {
    const [mode, setMode] = useState('signin')

    return (
        <div className="sidebar-tab-content">
            <div className="auth-toggle">
                <button
                    className={`auth-toggle-btn ${mode === 'signin' ? 'active' : ''}`}
                    onClick={() => setMode('signin')}
                >
                    Sign In
                </button>
                <button
                    className={`auth-toggle-btn ${mode === 'create' ? 'active' : ''}`}
                    onClick={() => setMode('create')}
                >
                    Create Account
                </button>
            </div>

            <div className="auth-form">
                {mode === 'create' && (
                    <input className="auth-input" type="text" placeholder="Display name" autoComplete="off" />
                )}
                <input className="auth-input" type="email" placeholder="Email address" autoComplete="off" />
                <input className="auth-input" type="password" placeholder="Password" />
                {mode === 'create' && (
                    <input className="auth-input" type="password" placeholder="Confirm password" />
                )}
                <button className="auth-submit">
                    {mode === 'signin' ? 'Sign In' : 'Create Account'}
                </button>
            </div>

            {mode === 'signin' && (
                <p className="auth-note">
                    Don't have an account?{' '}
                    <button className="auth-link" onClick={() => setMode('create')}>Create one</button>
                </p>
            )}
            {mode === 'create' && (
                <p className="auth-note">
                    Already have an account?{' '}
                    <button className="auth-link" onClick={() => setMode('signin')}>Sign in</button>
                </p>
            )}

            <div className="auth-benefits">
                <p className="info-heading" style={{ marginBottom: '0.5rem' }}>Why sign in?</p>
                <ul className="info-tips">
                    <li>Track your win / loss record</li>
                    <li>View your career guess history</li>
                    <li>Compete on leaderboards <em>(coming soon)</em></li>
                </ul>
            </div>
        </div>
    )
}

/* ── HISTORY ─────────────────────────────────────────── */
function HistoryTab() {
    return (
        <div className="sidebar-tab-content">
            <div className="coming-soon-box">
                <div className="coming-soon-road">
                    <div className="cs-spine" />
                    {[1, 2, 3].map(n => (
                        <div key={n} className="cs-stop">
                            <div className="cs-dot" />
                            <div className="cs-bar" style={{ width: `${40 + n * 20}%` }} />
                        </div>
                    ))}
                </div>
                <p className="coming-soon-title">History</p>
                <p className="coming-soon-text">
                    Sign in to track wins, losses, streaks, and your guess accuracy over time.
                </p>
                <div className="coming-soon-stats">
                    <div className="cs-stat">
                        <span className="cs-stat-val">—</span>
                        <span className="cs-stat-label">Played</span>
                    </div>
                    <div className="cs-stat">
                        <span className="cs-stat-val">—</span>
                        <span className="cs-stat-label">Won</span>
                    </div>
                    <div className="cs-stat">
                        <span className="cs-stat-val">—</span>
                        <span className="cs-stat-label">Streak</span>
                    </div>
                </div>
                <p className="coming-soon-badge">Coming Soon</p>
            </div>
        </div>
    )
}

/* ── SIDEBAR ─────────────────────────────────────────── */
function Sidebar({ open, onClose }) {
    const [tab, setTab] = useState('howto')

    return (
        <>
            <div className={`sidebar-backdrop ${open ? 'open' : ''}`} onClick={onClose} />
            <div className={`sidebar ${open ? 'open' : ''}`}>
                <div className="sidebar-header">
                    <span className="sidebar-brand">Journeyman</span>
                    <button className="sidebar-close" onClick={onClose} aria-label="Close">✕</button>
                </div>

                <div className="sidebar-tabs">
                    {TABS.map(t => (
                        <button
                            key={t.id}
                            className={`sidebar-tab-btn ${tab === t.id ? 'active' : ''}`}
                            onClick={() => setTab(t.id)}
                        >
                            {t.label}
                        </button>
                    ))}
                </div>

                <div className="sidebar-body">
                    {tab === 'howto'   && <HowToPlayTab />}
                    {tab === 'account' && <AccountTab />}
                    {tab === 'history' && <HistoryTab />}
                </div>
            </div>
        </>
    )
}

export default Sidebar
