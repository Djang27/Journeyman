import TeamList from "./team_list"
import React, {useState} from 'react'

function GameScreen({player, teams}) {
    const[guesses, set_guesses] = useState(Array(teams.length).fill(""))
    return (
        <div>
            <h2>Player: {player}</h2>
            <TeamList teams = {teams} />

            <button>Submit Guess</button>
        </div>
    )
}

export default GameScreen