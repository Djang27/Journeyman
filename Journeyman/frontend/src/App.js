import React, {useState} from 'react'
import StartScreen from "./components/start"
import GameScreen from "./components/game"
function App() {
    const [player, set_player] = useState("");
    const [teams, set_teams] = useState([]);
    const[game_start, set_game_status] = useState(false);
    const[guesses, set_guesses] = useState(Array(teams.length).fill(""))

    const start_game = () => {
    fetch("/new-game")
      .then(res => res.json())
      .then(data => {
        set_player(data.Player);
        set_teams(data.Teams);
        set_game_status(true);
      });
  };
    return(
      <div>
          {!game_start && (
            <StartScreen onStart = {start_game} />
          )}
          {game_start && (
            <GameScreen player = {player} teams = {teams} />
          )}
          
      </div>
   )
}

export default App