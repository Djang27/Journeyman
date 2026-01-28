function StartScreen ( {onStart} ) {
    return (
        <div>
            <h1>Welcome to Journeyman</h1>
            <button onClick = {onStart}> Start Game </button>
        </div>
    )
}

export default StartScreen