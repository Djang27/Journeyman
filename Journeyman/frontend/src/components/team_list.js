import { useState, useRef, useEffect } from 'react'
import Verdict from './verdict'

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

function Caret({ muted }) {
    // Drawn rather than a glyph: it recolours with state and never renders as a
    // different character on somebody else's machine.
    return (
        <svg className="team-caret" width="13" height="8" viewBox="0 0 13 8" aria-hidden="true">
            <path d="M1 1 L6.5 6.5 L12 1" fill="none" stroke={muted ? '#a89d88' : '#23201b'} strokeWidth="1.8" />
        </svg>
    )
}

function TeamSearch({ value, onChange, disabled }) {
    const [input, setInput] = useState("")
    const [open, setOpen] = useState(false)
    const [filtered, setFiltered] = useState([])
    const [highlighted, setHighlighted] = useState(-1)
    const containerRef = useRef(null)
    const inputRef = useRef(null)

    useEffect(() => {
        setInput(value ? toTitleCase(value) : "")
        setOpen(false)
    }, [value])

    // Opening shows everything. A pulldown that opens empty until you type is a
    // text box wearing a chevron, and somebody who cannot remember the name
    // needs the list.
    const openList = () => {
        if (disabled) return
        setFiltered(NBA_TEAMS)
        setHighlighted(-1)
        setOpen(true)
        inputRef.current?.focus()
    }

    const handleChange = (e) => {
        const q = e.target.value
        setInput(q)
        setHighlighted(-1)
        const needle = q.toLowerCase().trim()
        const matches = needle ? NBA_TEAMS.filter(t => t.includes(needle)) : NBA_TEAMS
        setFiltered(matches)
        setOpen(true)
        if (!needle) onChange("")
    }

    const select = (team) => {
        setInput(toTitleCase(team))
        setFiltered([])
        setOpen(false)
        setHighlighted(-1)
        onChange(team)
    }

    const handleKeyDown = (e) => {
        if (e.key === 'ArrowDown' && !open) {
            e.preventDefault()
            openList()
            return
        }
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
            <div
                className={`team-field ${open ? 'open' : ''}`}
                onClick={openList}
                aria-disabled={disabled}
            >
                <input
                    ref={inputRef}
                    type="text"
                    className="team-input"
                    value={input}
                    onChange={handleChange}
                    onKeyDown={handleKeyDown}
                    placeholder="Select a club"
                    disabled={disabled}
                    autoComplete="off"
                    spellCheck="false"
                    role="combobox"
                    aria-expanded={open}
                    aria-controls="team-options"
                />
                {!disabled && <Caret muted={!value} />}
            </div>
            {open && (
                <ul className="team-suggestions" id="team-options" role="listbox">
                    {filtered.length === 0 && <li className="team-empty">No club by that name</li>}
                    {filtered.map((t, i) => (
                        <li
                            key={t}
                            role="option"
                            aria-selected={i === highlighted}
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

// The route the stops sit on. Built from the stop count so it bends the right
// number of times, and drawn behind them in one path -- a road, not a rule with
// dots beside it.
//
// Percentages, not pixels: the same curve has to work at 320px and 700px, and a
// fixed path would either overflow a phone or float away from the markers on a
// desktop.
function roadPath(stops) {
    if (stops < 1) return ""

    const ROW = 100          // one stop's vertical share, in path units
    const LEFT = 18
    const RIGHT = 82
    const height = stops * ROW

    let d = `M 50 0`
    for (let i = 0; i < stops; i++) {
        const x = i % 2 === 0 ? LEFT : RIGHT
        const prevX = i === 0 ? 50 : (i - 1) % 2 === 0 ? LEFT : RIGHT
        const y = i * ROW + ROW * 0.42
        const prevY = i === 0 ? 0 : (i - 1) * ROW + ROW * 0.42
        const mid = (prevY + y) / 2
        d += ` C ${prevX} ${mid}, ${x} ${mid}, ${x} ${y}`
    }
    // Run the road off the bottom rather than stopping dead at the last stop.
    const lastX = (stops - 1) % 2 === 0 ? LEFT : RIGHT
    d += ` C ${lastX} ${height - ROW * 0.2}, 50 ${height - ROW * 0.1}, 50 ${height}`
    return d
}

function TeamList({ num_teams, hints, guesses, results, on_guess_change, on_submit, on_clear, game_over }) {
    const path = roadPath(num_teams)

    return (
        <div className="roadmap">
            <svg
                className="road-canvas"
                viewBox={`0 0 100 ${Math.max(num_teams, 1) * 100}`}
                preserveAspectRatio="none"
                aria-hidden="true"
            >
                <path className="road-shoulder" d={path} vectorEffect="non-scaling-stroke" />
                <path className="road-surface" d={path} vectorEffect="non-scaling-stroke" />
                <path className="road-centre" d={path} vectorEffect="non-scaling-stroke" />
            </svg>

            {Array.from({ length: num_teams }, (_, index) => {
                const result     = results[index]
                const cardClass  = result ? RESULT_COLORS[result] : ""
                const isLocked   = result === "green"
                // The conference comes from the server, which is the only
                // side that knows the answer. Deriving it here would mean
                // holding the teams in the browser again.
                const conf       = isLocked ? null : (hints?.[index] ?? null)
                const showClear  = !isLocked && !game_over && !!(guesses[index] ?? "")
                const bend       = index % 2 === 0 ? 'bend-left' : 'bend-right'

                return (
                    <div className={`road-stop ${bend}`} key={index}>
                        <div className={`stop-marker ${cardClass}`}>
                            {index + 1}
                        </div>

                        <div className={`stop-card ${cardClass}`}>
                            <span className="stop-number">
                                Stop {index + 1}
                                {conf && <span className={`conf-badge ${conf === "East" ? "east" : "west"}`}>{conf}</span>}
                            </span>

                            {isLocked ? (
                                // Set like a line in a table once it is settled:
                                // a club colour spine, the name, a double rule
                                // under it, and the verdict said in words.
                                <>
                                    <div className="stop-solved">
                                        <span className="stop-solved-spine"></span>
                                        <span className="stop-solved-name">{toTitleCase(guesses[index] ?? "")}</span>
                                    </div>
                                    <Verdict result={result} />
                                </>
                            ) : (
                                <>
                                    <TeamSearch
                                        value={guesses[index] ?? ""}
                                        onChange={(val) => on_guess_change(index, val)}
                                        disabled={game_over}
                                    />
                                    {/* The field already shows what they typed,
                                        so only the verdict is added -- repeating
                                        the guess under its own input reads as a
                                        rendering bug. */}
                                    {result && result !== 'green' && <Verdict result={result} />}
                                    <div className="stop-actions">
                                        {showClear && (
                                            <button
                                                className="clear-btn"
                                                onClick={() => on_clear(index)}
                                                aria-label="Clear guess"
                                            >
                                                Clear
                                            </button>
                                        )}
                                        <button
                                            className="guess-btn"
                                            onClick={() => on_submit(index)}
                                            disabled={game_over || !(guesses[index] ?? "").trim()}
                                        >
                                            Guess
                                        </button>
                                    </div>
                                </>
                            )}
                        </div>
                    </div>
                )
            })}
        </div>
    )
}

export default TeamList
