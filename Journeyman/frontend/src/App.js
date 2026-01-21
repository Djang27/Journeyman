import React, {useState, useEffect} from 'react'

function App() {
    const [player, set_player] = useState("")
    useEffect(() => {
        fetch("/new-game").then(
            (res) => res.json()
        ).then(
            data => {
                set_player(data.Player)
                console.log(data.Player)
            }
        )
    }, [])
    return(
      <div>

      </div>
   )
}

export default App