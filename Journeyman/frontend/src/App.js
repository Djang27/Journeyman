import React, { useState, useEffect, useRef } from 'react'
import StartScreen from "./components/start"
import GameScreen from "./components/game"
import Sidebar from "./components/Sidebar"
import UserMenu from "./components/UserMenu"
import { supabase } from './lib/supabase'
import { calculate_score } from './lib/scoring'
import './App.css'

const PLAYED_KEY = "journeyman_played"

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

function App() {
    const [player, set_player]               = useState("")
    const [teams, set_teams]                 = useState([])
    const [game_start, set_game_status]      = useState(false)
    const [guesses, set_guesses]             = useState([])
    const [results, set_results]             = useState([])
    const [wrong_guesses, set_wrong_guesses] = useState(0)
    const [hint_active, set_hint_active]     = useState(false)
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
    const hint_ref       = useRef(false)   // ref mirror of hint_active for the save effect

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
        })

        set_final_time(game_time)
        set_final_score(score)

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
            score,
        }).then(({ error }) => {
            if (error) console.error('Failed to save result:', error.message)
        })
    }, [has_won, has_lost])
    /* eslint-enable react-hooks/exhaustive-deps */

    const start_game = () => {
        set_loading(true)
        const played_ids    = get_played_ids()
        const exclude_param = played_ids.length ? `?exclude=${played_ids.join(",")}` : ""
        fetch(`/new-game${exclude_param}`)
            .then(res => res.json())
            .then(data => {
                set_player(data.Player)
                set_teams(data.Teams)
                set_guesses(Array(data.Teams.length).fill(""))
                set_results(Array(data.Teams.length).fill(null))
                set_wrong_guesses(0)
                set_hint_active(false)
                set_elapsed(0)
                set_final_time(null)
                set_final_score(null)
                hint_ref.current      = false
                result_saved.current  = false
                start_time_ref.current = Date.now()
                set_game_status(true)
                set_loading(false)
                record_played_id(data.PlayerID)
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
                if (data.result === "gray") set_wrong_guesses(prev => prev + 1)
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
        set_elapsed(0)
        set_final_time(null)
        set_final_score(null)
        hint_ref.current       = false
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
            {!game_start && <StartScreen onStart={start_game} />}
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
                    elapsed={elapsed}
                    final_time={final_time}
                    final_score={final_score}
                    on_play_again={reset_game}
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
