import React, {useState, useEffect} from 'react'

function App() {
    const [player, set_player] = useState("");
    const [teams, set_teams] = useState([]);
    const[game_start, set_game_status] = useState(false);

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
        <h1>Welcome to Journeyman</h1>

        {!game_start && (
             <button onClick = {start_game}>
                Start Game
            </button>
        )}

        {game_start && (
            <h2>Player: {player} Teams: {teams} </h2>
        )}
          
      </div>
   )
}

export default App