const NBA_TEAMS = [
    "atlanta hawks", "boston celtics", "brooklyn nets", "charlotte hornets",
    "chicago bulls", "cleveland cavaliers", "dallas mavericks", "denver nuggets",
    "detroit pistons", "golden state warriors", "houston rockets", "indiana pacers",
    "los angeles clippers", "los angeles lakers", "memphis grizzlies", "miami heat",
    "milwaukee bucks", "minnesota timberwolves", "new jersey nets", "new orleans hornets",
    "new orleans pelicans", "new orleans/oklahoma city hornets", "new york knicks",
    "oklahoma city thunder", "orlando magic", "philadelphia 76ers", "phoenix suns",
    "portland trail blazers", "sacramento kings", "san antonio spurs", "seattle supersonics",
    "toronto raptors", "utah jazz", "vancouver grizzlies", "washington bullets",
    "washington wizards"
].sort()

const RESULT_COLORS = {
    green: "correct",
    yellow: "close",
    gray: "wrong",
}

function TeamList({ teams, guesses, results, on_guess_change, on_submit, game_over }) {
    return (
        <div className="roadmap">
            <div className="road-spine"></div>
            <div className="road-dashes"></div>

            {teams.map((team, index) => {
                const result = results[index]
                const cardClass = result ? RESULT_COLORS[result] : ""
                const isLocked = result === "green"

                return (
                    <div className="road-stop" key={index}>
                        <div className={`stop-marker ${cardClass}`}>
                            {index + 1}
                        </div>

                        <div className={`stop-card ${cardClass}`}>
                            <span className="stop-number">Stop {index + 1}</span>

                            <select
                                className="team-select"
                                value={guesses[index] ?? ""}
                                onChange={(e) => on_guess_change(index, e.target.value)}
                                disabled={isLocked || game_over}
                            >
                                <option value="">— select a team —</option>
                                {NBA_TEAMS.map(t => (
                                    <option key={t} value={t}>{t.replace(/\b\w/g, c => c.toUpperCase())}</option>
                                ))}
                            </select>

                            <button
                                className="guess-btn"
                                onClick={() => on_submit(index)}
                                disabled={isLocked || game_over || !(guesses[index] ?? "").trim()}
                            >
                                Guess
                            </button>
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

export default TeamList
