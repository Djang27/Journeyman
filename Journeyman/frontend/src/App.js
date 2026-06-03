import React, { useState, useEffect } from 'react'
import StartScreen from "./components/start"
import GameScreen from "./components/game"
import Sidebar from "./components/Sidebar"
import { supabase } from './lib/supabase'
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
    const [player, set_player]           = useState("")
    const [teams, set_teams]             = useState([])
    const [game_start, set_game_status]  = useState(false)
    const [guesses, set_guesses]         = useState([])
    const [results, set_results]         = useState([])
    const [wrong_guesses, set_wrong_guesses] = useState(0)
    const [loading, set_loading]         = useState(false)
    const [show_sidebar, set_show_sidebar] = useState(false)
    const [user, set_user]               = useState(null)
    const [recovery_mode, set_recovery_mode] = useState(false)
    const MAX_WRONG_GUESSES = 3

    // Auth state listener — single source of truth for the current user
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

    const start_game = () => {
        set_loading(true)
        const played_ids = get_played_ids()
        const exclude_param = played_ids.length ? `?exclude=${played_ids.join(",")}` : ""
        fetch(`/new-game${exclude_param}`)
            .then(res => res.json())
            .then(data => {
                set_player(data.Player)
                set_teams(data.Teams)
                set_guesses(Array(data.Teams.length).fill(""))
                set_results(Array(data.Teams.length).fill(null))
                set_wrong_guesses(0)
                set_game_status(true)
                set_loading(false)
                record_played_id(data.PlayerID)
            })
    }

    const check_guess = (position) => {
        fetch("/check-guess", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                guess: guesses[position].toLowerCase().trim(),
                teams: teams,
                position: position,
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
                    set_wrong_guesses(prev => prev + 1)
                }
            })
    }

    const update_guess = (position, value) => {
        set_guesses(prev => {
            const updated = [...prev]
            updated[position] = value
            return updated
        })
    }

    const reset_game = () => {
        set_player("")
        set_teams([])
        set_guesses([])
        set_results([])
        set_wrong_guesses(0)
        set_game_status(false)
    }

    const has_won  = results.length > 0 && results.every(r => r === "green")
    const has_lost = wrong_guesses >= MAX_WRONG_GUESSES

    if (loading) {
        return (
            <div className="start-screen">
                <div className="loading-text">Loading journey...</div>
            </div>
        )
    }

    return (
        <div className="app-container">
            <button className="menu-btn" onClick={() => set_show_sidebar(true)} aria-label="Open menu">
                <span /><span /><span />
            </button>
            {!game_start && <StartScreen onStart={start_game} />}
            {game_start && (
                <GameScreen
                    player={player}
                    teams={teams}
                    guesses={guesses}
                    results={results}
                    on_guess_change={update_guess}
                    on_submit={check_guess}
                    has_won={has_won}
                    has_lost={has_lost}
                    wrong_guesses={wrong_guesses}
                    max_guesses={MAX_WRONG_GUESSES}
                    on_play_again={reset_game}
                />
            )}
            <Sidebar
                open={show_sidebar}
                onClose={() => set_show_sidebar(false)}
                user={user}
                recoveryMode={recovery_mode}
            />
        </div>
    )
}

export default App
