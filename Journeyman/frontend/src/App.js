import React, {useState, useEffect} from 'react'

function App() {
    const [player, set_player] = useState("")
    const [teams, set_teams] = useState([])
    useEffect(() => {
        fetch("/new-game").then(
            (res) => res.json()
        ).then(
            data => {
                set_player(data.Player)
                set_teams(data.Teams)
                console.log(data.Player)
                console.log(data.Teams)
            }
        )
    }, [])
    return(
      <div>
 
      </div>
   )
}

export default App