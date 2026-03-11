const RESULT_COLORS = {
    green: "#538d4e",
    yellow: "#b59f3b",
    gray: "#3a3a3c"
};

function TeamList( {teams, guesses, results, on_guess_change, on_submit} ) {
    return (
        <ul style = {{listStyle: "none", padding: 0}}>
            {teams.map((team, index) => {
                const result = results[index];
                const bgColor = result ? RESULT_COLORS[result] : "transparent";
                const isLocked = result === "green";

                return (
                    <li key = {index} style = {{marginBottom: "8px", display: "flex", alignItems: "center", gap: "8px"}}>
                        <span>Team {index + 1}:</span>
                        <input
                            type = "text"
                            value = {guesses[index] ?? ""}
                            onChange = {(e) => on_guess_change(index, e.target.value)}
                            disabled = {isLocked}
                            style = {{
                                backgroundColor: bgColor,
                                color: result ? "white" : "inherit",
                                border: "1px solid #ccc",
                                padding: "4px 8px",
                                borderRadius: "4px",
                            }}
                        />
                        <button
                            onClick = {() => on_submit(index)}
                            disabled = {isLocked || !(guesses[index] ?? "").trim()}
                        >
                            Guess
                        </button>
                        {result && (
                            <span style = {{ color: bgColor, fontWeight: "bold", textTransform: "capitalize"}}>
                                {result}
                            </span>
                        )}
                    </li>
                )
            })}
        </ul>
    )
}

export default TeamList