function TeamList( {teams} ) {
    return (
        <ul>
            {teams.map((team, index) => (
                <li key = {index}> {team} </li>
            ))}
        </ul>
    )
}

export default TeamList