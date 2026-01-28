import TeamList from "./team_list"

function GameScreen({player, teams}) {
    return (
        <div>
            <h2>Player: {player}</h2>
            <TeamList teams = {teams} />
        </div>
    )
}

export default GameScreen