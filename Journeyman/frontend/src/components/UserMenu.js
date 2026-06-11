import { useState, useRef, useEffect } from 'react'
import { supabase } from '../lib/supabase'

function UserMenu({ user, onOpenStats, onOpenHistory, onOpenAccount }) {
    const [open, setOpen] = useState(false)
    const ref = useRef(null)

    const displayName = user?.user_metadata?.display_name || user?.email?.split('@')[0] || 'Player'
    const initial = displayName[0].toUpperCase()

    useEffect(() => {
        const handler = (e) => {
            if (ref.current && !ref.current.contains(e.target)) setOpen(false)
        }
        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [])

    async function handleSignOut() {
        setOpen(false)
        await supabase.auth.signOut()
    }

    return (
        <div ref={ref} className="user-menu">
            <button
                className="user-avatar-btn"
                onClick={() => setOpen(o => !o)}
                aria-label="Account menu"
                aria-expanded={open}
            >
                {initial}
            </button>

            {open && (
                <div className="user-dropdown">
                    <div className="user-dropdown-header">
                        <p className="user-dropdown-name">{displayName}</p>
                        <p className="user-dropdown-email">{user.email}</p>
                    </div>

                    <div className="user-dropdown-divider" />

                    <button className="user-dropdown-item" onClick={() => { setOpen(false); onOpenStats() }}>
                        <span className="user-dropdown-icon">◈</span>
                        Stats
                    </button>
                    <button className="user-dropdown-item" onClick={() => { setOpen(false); onOpenHistory() }}>
                        <span className="user-dropdown-icon">▤</span>
                        History
                    </button>
                    <button className="user-dropdown-item" onClick={() => { setOpen(false); onOpenAccount() }}>
                        <span className="user-dropdown-icon">◎</span>
                        Account Settings
                    </button>

                    <div className="user-dropdown-divider" />

                    <button className="user-dropdown-item signout" onClick={handleSignOut}>
                        <span className="user-dropdown-icon">→</span>
                        Sign Out
                    </button>
                </div>
            )}
        </div>
    )
}

export default UserMenu
