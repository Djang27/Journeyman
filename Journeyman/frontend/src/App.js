import React, { useState, useEffect, useRef } from 'react'
import StartScreen from "./components/start"
import GameScreen from "./components/game"
import Sidebar from "./components/Sidebar"
import UserMenu from "./components/UserMenu"
import { supabase, authAvailable } from './lib/supabase'
import * as api from './lib/api'
import './App.css'

// The game is driven entirely by the server from here on. This component holds
// no answer, computes no score, and writes no result -- it renders whatever the
// last session response said and sends the next action.
//
// What is left in localStorage is a cache, not a rule. The daily gate is
// enforced by a unique index in the database; this only spares a signed-in
// player a pointless request, and remembers the outcome for signed-out players
// whom the database cannot identify.

const PLAYED_KEY = "journeyman_played"
const today_str  = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(new Date())
const DAILY_KEY  = `journeyman_daily_${today_str}`

function get_played_ids() {
    try {
        return JSON.parse(localStorage.getItem(PLAYED_KEY) || "[]")
    } catch {
        return []
    }
}

function record_played_id(id) {
    if (id === undefined || id === null) return
    const played = get_played_ids()
    if (!played.includes(id)) {
        try { localStorage.setItem(PLAYED_KEY, JSON.stringify([...played, id])) } catch {}
    }
}

function get_daily_done() {
    try { return !!localStorage.getItem(DAILY_KEY) } catch { return false }
}

function save_daily_result(result, score) {
    try { localStorage.setItem(DAILY_KEY, JSON.stringify({ result, score })) } catch {}
}

const BLANK = {
    session_id: null,
    player: "",
    num_teams: 0,
    results: [],
    hints: null,
    wrong_guesses: 0,
    max_wrong_guesses: 3,
    hint_used: false,
    hard_mode: false,
    status: "active",
    teams: null,
    score: null,
    elapsed_seconds: 0,
}

function App() {
    // The server's view of the game. Everything rendered comes from here.
    const [game, set_game]                   = useState(BLANK)
    const [guesses, set_guesses]             = useState([])
    const [game_start, set_game_status]      = useState(false)
    const [game_mode, set_game_mode]         = useState('unlimited')
    const [day_number, set_day_number]       = useState(1)
    const [daily_done, set_daily_done]       = useState(get_daily_done)
    const [loading, set_loading]             = useState(false)
    const [error, set_error]                 = useState(null)
    const [show_sidebar, set_show_sidebar]   = useState(false)
    const [sidebar_tab, set_sidebar_tab]     = useState('howto')
    const [user, set_user]                   = useState(null)
    const [recovery_mode, set_recovery_mode] = useState(false)
    const [elapsed, set_elapsed]             = useState(0)

    const start_time_ref = useRef(null)
    const timer_ref      = useRef(null)

    const has_won   = game.status === 'won'
    const has_lost  = game.status === 'lost'
    const game_over = has_won || has_lost

    useEffect(() => {
        // No Supabase configured: nobody can be signed in, and asking would
        // throw. The game itself talks only to /api, so it plays on.
        if (!authAvailable) return undefined

        supabase.auth.getSession().then(({ data: { session } }) => {
            set_user(session?.user ?? null)
        })
        const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
            set_user(session?.user ?? null)
            if (event === 'PASSWORD_RECOVERY') {
                set_recovery_mode(true)
                set_show_sidebar(true)
            } else {
                set_recovery_mode(false)
            }
        })
        return () => subscription.unsubscribe()
    }, [])

    // Live timer. Display only -- the score is timed by the server clock, so a
    // paused tab or a fiddled system clock changes what is shown and nothing else.
    useEffect(() => {
        if (!game_start || game_over || !start_time_ref.current) return
        const id = setInterval(() => {
            set_elapsed(Math.floor((Date.now() - start_time_ref.current) / 1000))
        }, 500)
        timer_ref.current = id
        return () => clearInterval(id)
    }, [game_start, game_over])

    function apply(session) {
        set_game(prev => ({ ...BLANK, ...prev, ...session }))
        set_guesses(prev => {
            const next = Array(session.num_teams ?? prev.length).fill("")
            // Keep what the player typed in slots they have not solved.
            return next.map((_, i) => (session.results?.[i] === 'green' ? "" : (prev[i] ?? "")))
        })
    }

    const start_game = async (mode = 'unlimited') => {
        set_loading(true)
        set_error(null)
        set_game_mode(mode)

        try {
            const session = await api.start_game({
                mode,
                exclude: mode === 'daily' ? [] : get_played_ids(),
            })

            set_game({ ...BLANK, ...session })
            set_guesses(Array(session.num_teams).fill(""))
            set_elapsed(0)
            start_time_ref.current = Date.now()
            if (session.day_number) set_day_number(session.day_number)
            set_game_status(true)
        } catch (err) {
            if (err.is_already_played) {
                set_daily_done(true)
                set_error("You have already played today's puzzle.")
            } else {
                set_error(err.message)
            }
        } finally {
            set_loading(false)
        }
    }

    const check_guess = async (position) => {
        const guess = (guesses[position] ?? "").trim()
        if (!guess || !game.session_id) return

        try {
            const session = await api.submit_guess(game.session_id, position, guess)
            apply(session)
            finish_if_over(session)
        } catch (err) {
            set_error(err.message)
        }
    }

    function finish_if_over(session) {
        if (session.status === 'active') return
        clearInterval(timer_ref.current)
        if (game_mode === 'daily') {
            save_daily_result(session.status === 'won' ? 'win' : 'loss', session.score)
            set_daily_done(true)
        }
        if (game_mode !== 'daily') record_played_id(session.player_id)
    }

    const toggle_hard_mode = async () => {
        if (!game.session_id) return
        try {
            apply(await api.set_hard_mode(game.session_id, !game.hard_mode))
        } catch (err) {
            set_error(err.message)
        }
    }

    const update_guess = (position, value) => {
        set_guesses(prev => {
            const updated = [...prev]
            updated[position] = value
            return updated
        })
    }

    const clear_guess = (position) => {
        set_guesses(prev => {
            const updated = [...prev]
            updated[position] = ""
            return updated
        })
    }

    const activate_hint = async () => {
        if (!game.session_id) return
        try {
            apply(await api.use_hint(game.session_id))
        } catch (err) {
            set_error(err.message)
        }
    }

    const reset_game = () => {
        clearInterval(timer_ref.current)
        set_game(BLANK)
        set_guesses([])
        set_elapsed(0)
        set_error(null)
        start_time_ref.current = null
        set_game_status(false)
    }

    function open_sidebar(tab = 'howto') {
        set_sidebar_tab(tab)
        set_show_sidebar(true)
    }

    if (loading) {
        return (
            <div className="start-screen">
                <div className="loading-text">Loading journey...</div>
            </div>
        )
    }

    return (
        <div className="app-container">
            <button className="menu-btn" onClick={() => open_sidebar()} aria-label="Open menu">
                <span /><span /><span />
            </button>
            {user && (
                <UserMenu
                    user={user}
                    onOpenStats={() => open_sidebar('stats')}
                    onOpenHistory={() => open_sidebar('history')}
                    onOpenAccount={() => open_sidebar('account')}
                />
            )}
            {error && (
                <div className="app-error" role="alert" onClick={() => set_error(null)}>
                    {error}
                </div>
            )}
            {!game_start && (
                <StartScreen
                    on_start_daily={() => start_game('daily')}
                    on_start_unlimited={() => start_game('unlimited')}
                    daily_done={daily_done}
                    day_number={day_number}
                />
            )}
            {game_start && (
                <GameScreen
                    player={game.player}
                    num_teams={game.num_teams}
                    teams={game.teams}
                    hints={game.hints}
                    guesses={guesses}
                    results={game.results}
                    on_guess_change={update_guess}
                    on_submit={check_guess}
                    on_clear={clear_guess}
                    has_won={has_won}
                    has_lost={has_lost}
                    wrong_guesses={game.wrong_guesses}
                    max_guesses={game.max_wrong_guesses}
                    hint_active={game.hint_used}
                    on_hint={activate_hint}
                    hard_mode={game.hard_mode}
                    on_hard_mode_toggle={toggle_hard_mode}
                    elapsed={elapsed}
                    final_time={game_over ? game.elapsed_seconds : null}
                    final_score={game_over ? game.score : null}
                    on_play_again={reset_game}
                    game_mode={game_mode}
                    day_number={day_number}
                />
            )}
            <Sidebar
                open={show_sidebar}
                onClose={() => set_show_sidebar(false)}
                user={user}
                recoveryMode={recovery_mode}
                initialTab={sidebar_tab}
            />
        </div>
    )
}

export default App
