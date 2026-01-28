function TeamList( {teams} ) {
    return (
        <ul>
            {teams.map((team, index) => (
                <li key = {index}> Team {index+1}:
                <input type = "text" />
                 </li>
            ))}
        </ul>
    )
}

export default TeamList