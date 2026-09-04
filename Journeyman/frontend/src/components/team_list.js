import { useState, useRef, useEffect } from 'react'

const NBA_TEAMS = [
    "atlanta hawks", "boston celtics", "brooklyn nets", "charlotte bobcats", "charlotte hornets",
    "chicago bulls", "cleveland cavaliers", "dallas mavericks", "denver nuggets",
    "detroit pistons", "golden state warriors", "houston rockets", "indiana pacers",
    "los angeles clippers", "los angeles lakers", "memphis grizzlies", "miami heat",
    "milwaukee bucks", "minnesota timberwolves", "new jersey nets", "new orleans hornets",
    "new orleans pelicans", "new york knicks",
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

function toTitleCase(str) {
    return str.replace(/\b\w/g, c => c.toUpperCase())
}

function TeamSearch({ value, onChange, disabled }) {
    const [input, setInput] = useState("")
    const [open, setOpen] = useState(false)
    const [filtered, setFiltered] = useState([])
    const [highlighted, setHighlighted] = useState(-1)
    const containerRef = useRef(null)

    useEffect(() => {
        setInput(value ? toTitleCase(value) : "")
        setOpen(false)
    }, [value])

    const handleChange = (e) => {
        const q = e.target.value
        setInput(q)
        setHighlighted(-1)
        if (q.trim().length > 0) {
            const matches = NBA_TEAMS.filter(t => t.includes(q.toLowerCase().trim()))
            setFiltered(matches)
            setOpen(matches.length > 0)
        } else {
            setFiltered([])
            setOpen(false)
            onChange("")
        }
    }

    const select = (team) => {
        setInput(toTitleCase(team))
        setFiltered([])
        setOpen(false)
        setHighlighted(-1)
        onChange(team)
    }

    const handleKeyDown = (e) => {
        if (!open) return
        if (e.key === 'ArrowDown') {
            e.preventDefault()
            setHighlighted(h => Math.min(h + 1, filtered.length - 1))
        } else if (e.key === 'ArrowUp') {
            e.preventDefault()
            setHighlighted(h => Math.max(h - 1, 0))
        } else if (e.key === 'Enter' && highlighted >= 0) {
            e.preventDefault()
            select(filtered[highlighted])
        } else if (e.key === 'Escape') {
            setOpen(false)
        }
    }

    useEffect(() => {
        const handler = (e) => {
            if (containerRef.current && !containerRef.current.contains(e.target)) {
                setOpen(false)
            }
        }
        document.addEventListener('mousedown', handler)
        return () => document.removeEventListener('mousedown', handler)
    }, [])

    return (
        <div ref={containerRef} className="team-search">
            <input
                type="text"
                className="team-input"
                value={input}
                onChange={handleChange}
                onKeyDown={handleKeyDown}
                placeholder="Type city or team name..."
                disabled={disabled}
                autoComplete="off"
                spellCheck="false"
            />
            {open && (
                <ul className="team-suggestions">
                    {filtered.map((t, i) => (
                        <li
                            key={t}
                            className={i === highlighted ? 'highlighted' : ''}
                            onMouseDown={() => select(t)}
                            onMouseEnter={() => setHighlighted(i)}
                        >
                            {toTitleCase(t)}
                        </li>
                    ))}
                </ul>
            )}
        </div>
    )
}

function TeamList({ num_teams, hints, guesses, results, on_guess_change, on_submit, on_clear, game_over }) {
    return (
        <div className="roadmap">
            <div className="road-spine"></div>
            <div className="road-dashes"></div>

            {Array.from({ length: num_teams }, (_, index) => {
                const result     = results[index]
                const cardClass  = result ? RESULT_COLORS[result] : ""
                const isLocked   = result === "green"
                // The conference comes from the server, which is the only
                // side that knows the answer. Deriving it here would mean
                // holding the teams in the browser again.
                const conf       = isLocked ? null : (hints?.[index] ?? null)
                const showClear  = !isLocked && !game_over && !!(guesses[index] ?? "")

                return (
                    <div className="road-stop" key={index}>
                        <div className={`stop-marker ${cardClass}`}>
                            {index + 1}
                        </div>

                        <div className={`stop-card ${cardClass}`}>
                            <span className="stop-number">Stop {index + 1}</span>

                            <TeamSearch
                                value={guesses[index] ?? ""}
                                onChange={(val) => on_guess_change(index, val)}
                                disabled={isLocked || game_over}
                            />

                            {showClear && (
                                <button
                                    className="clear-btn"
                                    onClick={() => on_clear(index)}
                                    aria-label="Clear guess"
                                >
                                    ✕
                                </button>
                            )}

                            {conf && (
                                <span className={`conf-badge ${conf === "East" ? "east" : "west"}`}>
                                    {conf}
                                </span>
                            )}

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
