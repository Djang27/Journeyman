import React, { useState, useEffect, useRef } from 'react'
import StartScreen from "./components/start"
import GameScreen from "./components/game"
import Sidebar from "./components/Sidebar"
import UserMenu from "./components/UserMenu"
import { supabase } from './lib/supabase'
import { calculate_score } from './lib/scoring'
import './App.css'

const PLAYED_KEY = "journeyman_played"
const today_str  = new Date().toISOString().slice(0, 10)
const DAILY_KEY  = `journeyman_daily_${today_str}`

function get_played_ids() {
    try {
        return JSON.parse(localStorage.getItem(PLAYED_KEY) || "[]")
    } catch {
        return []
    }
}

function record_played_id(id) {
    const played = get_played_ids()
    if (!played.includes(id)) {
        localStorage.setItem(PLAYED_KEY, JSON.stringify([...played, id]))
    }
}

function get_daily_done() {
    try { return !!localStorage.getItem(DAILY_KEY) } catch { return false }
}

function save_daily_result(result, score) {
    try { localStorage.setItem(DAILY_KEY, JSON.stringify({ result, score })) } catch {}
}

function App() {
    const [player, set_player]               = useState("")
    const [teams, set_teams]                 = useState([])
    const [game_start, set_game_status]      = useState(false)
    const [guesses, set_guesses]             = useState([])
    const [results, set_results]             = useState([])
    const [wrong_guesses, set_wrong_guesses] = useState(0)
    const [hint_active, set_hint_active]     = useState(false)
    const [hard_mode, set_hard_mode]         = useState(false)
    const [game_mode, set_game_mode]         = useState('unlimited')
    const [day_number, set_day_number]       = useState(1)
    const [daily_done, set_daily_done]       = useState(get_daily_done)
    const [loading, set_loading]             = useState(false)
    const [show_sidebar, set_show_sidebar]   = useState(false)
    const [sidebar_tab, set_sidebar_tab]     = useState('howto')
    const [user, set_user]                   = useState(null)
    const [recovery_mode, set_recovery_mode] = useState(false)
    const [elapsed, set_elapsed]             = useState(0)
    const [final_time, set_final_time]       = useState(null)
    const [final_score, set_final_score]     = useState(null)

    const start_time_ref = useRef(null)
    const timer_ref      = useRef(null)
    const result_saved   = useRef(false)
    const hint_ref       = useRef(false)
    const hard_mode_ref  = useRef(false)
    const game_mode_ref  = useRef('unlimited')

    const MAX_WRONG_GUESSES = 3

    useEffect(() => {
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

    // Live timer — ticks every 500 ms while game is running
    useEffect(() => {
        if (!game_start || !start_time_ref.current) return
        const id = setInterval(() => {
            set_elapsed(Math.floor((Date.now() - start_time_ref.current) / 1000))
        }, 500)
        timer_ref.current = id
        return () => clearInterval(id)
    }, [game_start])

    const has_won  = results.length > 0 && results.every(r => r === "green")
    const has_lost = wrong_guesses >= MAX_WRONG_GUESSES

    /* eslint-disable react-hooks/exhaustive-deps */
    useEffect(() => {
        if (!game_start || (!has_won && !has_lost)) return

        clearInterval(timer_ref.current)
        const game_time = Math.floor((Date.now() - start_time_ref.current) / 1000)
        const result    = has_won ? 'win' : 'loss'
        const score     = calculate_score({
            result,
            time_seconds:   game_time,
            wrong_guesses,
            hint_used:      hint_ref.current,
            hard_mode:      hard_mode_ref.current,
        })

        set_final_time(game_time)
        set_final_score(score)

        if (game_mode_ref.current === 'daily') {
            save_daily_result(result, score)
            set_daily_done(true)
        }

        if (!user || result_saved.current) return
        result_saved.current = true
        supabase.from('game_results').insert({
            user_id:      user.id,
            player_name:  player,
            result,
            wrong_guesses,
            num_teams:    teams.length,
            time_seconds: game_time,
            hint_used:    hint_ref.current,
            hard_mode:    hard_mode_ref.current,
            score,
        }).then(({ error }) => {
            if (error) console.error('Failed to save result:', error.message)
        })
    }, [has_won, has_lost])
    /* eslint-enable react-hooks/exhaustive-deps */

    const start_game = (mode = 'unlimited') => {
        set_loading(true)
        set_game_mode(mode)
        game_mode_ref.current = mode

        const url = mode === 'daily'
            ? '/daily-game'
            : `/new-game${get_played_ids().length ? `?exclude=${get_played_ids().join(",")}` : ""}`

        fetch(url)
            .then(res => res.json())
            .then(data => {
                set_player(data.Player)
                set_teams(data.Teams)
                set_guesses(Array(data.Teams.length).fill(""))
                set_results(Array(data.Teams.length).fill(null))
                set_wrong_guesses(0)
                set_hint_active(false)
                set_hard_mode(false)
                set_elapsed(0)
                set_final_time(null)
                set_final_score(null)
                hint_ref.current       = false
                hard_mode_ref.current  = false
                result_saved.current   = false
                start_time_ref.current = Date.now()
                if (data.DayNumber) set_day_number(data.DayNumber)
                set_game_status(true)
                set_loading(false)
                if (mode !== 'daily') record_played_id(data.PlayerID)
            })
    }

    const check_guess = (position) => {
        fetch("/check-guess", {
            method:  "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                guess:    guesses[position].toLowerCase().trim(),
                teams,
                position,
            }),
        })
            .then(res => res.json())
            .then(data => {
                set_results(prev => {
                    const updated = [...prev]
                    updated[position] = data.result
                    return updated
                })
                if (data.result === "gray") {
                    set_wrong_guesses(prev =>
                        hard_mode_ref.current ? MAX_WRONG_GUESSES : prev + 1
                    )
                }
            })
    }

    const toggle_hard_mode = () => {
        set_hard_mode(prev => {
            const next = !prev
            hard_mode_ref.current = next
            return next
        })
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
        set_results(prev => {
            const updated = [...prev]
            updated[position] = null
            return updated
        })
    }

    const activate_hint = () => {
        hint_ref.current = true
        set_hint_active(true)
    }

    const reset_game = () => {
        clearInterval(timer_ref.current)
        set_player("")
        set_teams([])
        set_guesses([])
        set_results([])
        set_wrong_guesses(0)
        set_hint_active(false)
        set_hard_mode(false)
        set_elapsed(0)
        set_final_time(null)
        set_final_score(null)
        hint_ref.current       = false
        hard_mode_ref.current  = false
        result_saved.current   = false
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
                    player={player}
                    teams={teams}
                    guesses={guesses}
                    results={results}
                    on_guess_change={update_guess}
                    on_submit={check_guess}
                    on_clear={clear_guess}
                    has_won={has_won}
                    has_lost={has_lost}
                    wrong_guesses={wrong_guesses}
                    max_guesses={MAX_WRONG_GUESSES}
                    hint_active={hint_active}
                    on_hint={activate_hint}
                    hard_mode={hard_mode}
                    on_hard_mode_toggle={toggle_hard_mode}
                    elapsed={elapsed}
                    final_time={final_time}
                    final_score={final_score}
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
