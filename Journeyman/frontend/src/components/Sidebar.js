import { useState, useEffect } from 'react'
import { supabase } from '../lib/supabase'

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
function AccountTab({ user, recoveryMode }) {
    const [view, setView] = useState('signin')
    const [displayName, setDisplayName] = useState('')
    const [email, setEmail]             = useState('')
    const [password, setPassword]       = useState('')
    const [confirm, setConfirm]         = useState('')
    const [loading, setLoading]         = useState(false)
    const [error, setError]             = useState('')
    const [message, setMessage]         = useState('')

    // Sync view with external auth state changes
    useEffect(() => {
        if (recoveryMode) {
            setView('set_password')
            setError('')
            setMessage('')
        } else if (user) {
            setView('profile')
        } else {
            setView('signin')
        }
        // Clear sensitive fields whenever the view resets externally
        setPassword('')
        setConfirm('')
        setError('')
    }, [user, recoveryMode])

    function clearForm() {
        setDisplayName('')
        setEmail('')
        setPassword('')
        setConfirm('')
        setError('')
        setMessage('')
    }

    function switchTo(v) {
        clearForm()
        setView(v)
    }

    // ── Sign in ────────────────────────────────────────
    async function handleSignIn(e) {
        e.preventDefault()
        setError('')
        setLoading(true)
        const { error: err } = await supabase.auth.signInWithPassword({ email, password })
        setLoading(false)
        setPassword('')
        if (err) {
            // Deliberately vague — don't reveal whether the email exists
            setError('Invalid email or password.')
        }
        // On success, App.js onAuthStateChange updates user → view switches via useEffect
    }

    // ── Sign up ────────────────────────────────────────
    async function handleSignUp(e) {
        e.preventDefault()
        setError('')
        if (password.length < 8) {
            setError('Password must be at least 8 characters.')
            return
        }
        if (password !== confirm) {
            setError('Passwords do not match.')
            return
        }
        setLoading(true)
        const { error: err } = await supabase.auth.signUp({
            email,
            password,
            options: {
                data: { display_name: displayName.trim() || email.split('@')[0] },
            },
        })
        setLoading(false)
        setPassword('')
        setConfirm('')
        if (err) {
            setError(err.message)
        } else {
            setView('check_email')
        }
    }

    // ── Forgot password ────────────────────────────────
    async function handleForgot(e) {
        e.preventDefault()
        setError('')
        setLoading(true)
        const { error: err } = await supabase.auth.resetPasswordForEmail(email, {
            redirectTo: window.location.origin,
        })
        setLoading(false)
        if (err) {
            setError(err.message)
        } else {
            setMessage('Password reset email sent. Check your inbox.')
            setView('check_email')
        }
    }

    // ── Set new password (recovery flow) ──────────────
    async function handleSetPassword(e) {
        e.preventDefault()
        setError('')
        if (password.length < 8) {
            setError('Password must be at least 8 characters.')
            return
        }
        if (password !== confirm) {
            setError('Passwords do not match.')
            return
        }
        setLoading(true)
        const { error: err } = await supabase.auth.updateUser({ password })
        setLoading(false)
        setPassword('')
        setConfirm('')
        if (err) {
            setError(err.message)
        } else {
            setMessage('Password updated successfully.')
            setView('profile')
        }
    }

    // ── Sign out ───────────────────────────────────────
    async function handleSignOut() {
        setLoading(true)
        await supabase.auth.signOut()
        setLoading(false)
        clearForm()
    }

    // ── Render helpers ─────────────────────────────────
    const displayedName = user?.user_metadata?.display_name || user?.email?.split('@')[0] || 'Player'

    return (
        <div className="sidebar-tab-content">

            {/* ── Profile ── */}
            {view === 'profile' && (
                <div className="auth-profile">
                    <div className="auth-avatar">{displayedName[0].toUpperCase()}</div>
                    <p className="auth-profile-name">{displayedName}</p>
                    <p className="auth-profile-email">{user?.email}</p>
                    {message && <p className="auth-success">{message}</p>}
                    <button className="auth-submit" onClick={handleSignOut} disabled={loading}>
                        {loading ? 'Signing out…' : 'Sign Out'}
                    </button>
                </div>
            )}

            {/* ── Set new password (recovery) ── */}
            {view === 'set_password' && (
                <>
                    <p className="auth-intro">Choose a new password for your account.</p>
                    <form className="auth-form" onSubmit={handleSetPassword}>
                        <input className="auth-input" type="password" placeholder="New password (min 8 chars)"
                            value={password} onChange={e => setPassword(e.target.value)} required autoFocus />
                        <input className="auth-input" type="password" placeholder="Confirm new password"
                            value={confirm} onChange={e => setConfirm(e.target.value)} required />
                        {error && <p className="auth-error">{error}</p>}
                        <button className="auth-submit" type="submit" disabled={loading}>
                            {loading ? 'Saving…' : 'Set New Password'}
                        </button>
                    </form>
                </>
            )}

            {/* ── Check email ── */}
            {view === 'check_email' && (
                <div className="auth-check-email">
                    <div className="auth-email-icon">✉</div>
                    <p className="auth-profile-name">Check your inbox</p>
                    <p className="auth-intro">{message || 'We sent a verification link to your email. Click it to activate your account.'}</p>
                    <button className="auth-link-btn" onClick={() => switchTo('signin')}>
                        Back to Sign In
                    </button>
                </div>
            )}

            {/* ── Sign in ── */}
            {view === 'signin' && (
                <>
                    <div className="auth-toggle">
                        <button className="auth-toggle-btn active" onClick={() => switchTo('signin')}>Sign In</button>
                        <button className="auth-toggle-btn" onClick={() => switchTo('signup')}>Create Account</button>
                    </div>
                    <form className="auth-form" onSubmit={handleSignIn}>
                        <input className="auth-input" type="email" placeholder="Email address"
                            value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" />
                        <input className="auth-input" type="password" placeholder="Password"
                            value={password} onChange={e => setPassword(e.target.value)} required autoComplete="current-password" />
                        {error && <p className="auth-error">{error}</p>}
                        <button className="auth-submit" type="submit" disabled={loading}>
                            {loading ? 'Signing in…' : 'Sign In'}
                        </button>
                    </form>
                    <button className="auth-link-btn" onClick={() => switchTo('forgot')}>
                        Forgot password?
                    </button>
                    <p className="auth-note">
                        No account?{' '}
                        <button className="auth-link" onClick={() => switchTo('signup')}>Create one</button>
                    </p>
                </>
            )}

            {/* ── Sign up ── */}
            {view === 'signup' && (
                <>
                    <div className="auth-toggle">
                        <button className="auth-toggle-btn" onClick={() => switchTo('signin')}>Sign In</button>
                        <button className="auth-toggle-btn active" onClick={() => switchTo('signup')}>Create Account</button>
                    </div>
                    <form className="auth-form" onSubmit={handleSignUp}>
                        <input className="auth-input" type="text" placeholder="Display name (optional)"
                            value={displayName} onChange={e => setDisplayName(e.target.value)} autoComplete="nickname" />
                        <input className="auth-input" type="email" placeholder="Email address"
                            value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" />
                        <input className="auth-input" type="password" placeholder="Password (min 8 chars)"
                            value={password} onChange={e => setPassword(e.target.value)} required autoComplete="new-password" />
                        <input className="auth-input" type="password" placeholder="Confirm password"
                            value={confirm} onChange={e => setConfirm(e.target.value)} required autoComplete="new-password" />
                        {error && <p className="auth-error">{error}</p>}
                        <button className="auth-submit" type="submit" disabled={loading}>
                            {loading ? 'Creating account…' : 'Create Account'}
                        </button>
                    </form>
                    <p className="auth-note">
                        Already have an account?{' '}
                        <button className="auth-link" onClick={() => switchTo('signin')}>Sign in</button>
                    </p>
                </>
            )}

            {/* ── Forgot password ── */}
            {view === 'forgot' && (
                <>
                    <p className="auth-intro">Enter your email and we'll send you a password reset link.</p>
                    <form className="auth-form" onSubmit={handleForgot}>
                        <input className="auth-input" type="email" placeholder="Email address"
                            value={email} onChange={e => setEmail(e.target.value)} required autoComplete="email" autoFocus />
                        {error && <p className="auth-error">{error}</p>}
                        <button className="auth-submit" type="submit" disabled={loading}>
                            {loading ? 'Sending…' : 'Send Reset Link'}
                        </button>
                    </form>
                    <button className="auth-link-btn" onClick={() => switchTo('signin')}>
                        Back to Sign In
                    </button>
                </>
            )}

        </div>
    )
}

/* ── HISTORY ─────────────────────────────────────────── */
function HistoryTab({ user }) {
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
                    {user
                        ? 'Your win/loss history and streaks will appear here soon.'
                        : 'Sign in to track wins, losses, streaks, and your guess accuracy over time.'}
                </p>
                <div className="coming-soon-stats">
                    <div className="cs-stat"><span className="cs-stat-val">—</span><span className="cs-stat-label">Played</span></div>
                    <div className="cs-stat"><span className="cs-stat-val">—</span><span className="cs-stat-label">Won</span></div>
                    <div className="cs-stat"><span className="cs-stat-val">—</span><span className="cs-stat-label">Streak</span></div>
                </div>
                <p className="coming-soon-badge">Coming Soon</p>
            </div>
        </div>
    )
}

/* ── SIDEBAR ─────────────────────────────────────────── */
function Sidebar({ open, onClose, user, recoveryMode }) {
    const [tab, setTab] = useState('howto')

    // Auto-switch to Account tab when a recovery link is detected
    useEffect(() => {
        if (recoveryMode && open) setTab('account')
    }, [recoveryMode, open])

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
                    {tab === 'account' && <AccountTab user={user} recoveryMode={recoveryMode} />}
                    {tab === 'history' && <HistoryTab user={user} />}
                </div>
            </div>
        </>
    )
}

export default Sidebar
