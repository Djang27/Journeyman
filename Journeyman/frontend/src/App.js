import React, { useState } from 'react'
import StartScreen from "./components/start"
import GameScreen from "./components/game"
import './App.css'

function App() {
    const [player, set_player] = useState("")
    const [teams, set_teams] = useState([])
    const [game_start, set_game_status] = useState(false)
    const [guesses, set_guesses] = useState([])
    const [results, set_results] = useState([])
    const [loading, set_loading] = useState(false)

    const start_game = () => {
        set_loading(true)
        fetch("/new-game")
            .then(res => res.json())
            .then(data => {
                set_player(data.Player)
                set_teams(data.Teams)
                set_guesses(Array(data.Teams.length).fill(""))
                set_results(Array(data.Teams.length).fill(null))
                set_game_status(true)
                set_loading(false)
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
        set_game_status(false)
    }

    const has_won = results.length > 0 && results.every(r => r === "green")

    if (loading) {
        return (
            <div className="start-screen">
                <div className="loading-text">Loading journey...</div>
            </div>
        )
    }

    return (
        <div className="app-container">
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
                    on_play_again={reset_game}
                />
            )}
        </div>
    )
}

export default App