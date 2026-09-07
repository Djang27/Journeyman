import { useState } from 'react'
import { VerdictKey } from './verdict'

// The front page of the register.
//
// It was a logo and two buttons on an empty field, which is a splash screen
// rather than a paper. A front page has a masthead, a lead, a standings column
// and a footer rail -- and all four are things a player actually wants before
// they start: what today's puzzle is, how they did, who is ahead, what else
// there is to read.

const MONTHS = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
]

function issueDate() {
    // Eastern, matching the puzzle rollover, so the date on the masthead is the
    // date of the puzzle beneath it.
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'America/New_York', year: 'numeric', month: 'numeric', day: 'numeric',
    }).formatToParts(new Date())
    const get = (t) => Number(parts.find(p => p.type === t)?.value)
    const y = get('year'), m = get('month'), d = get('day')
    const weekday = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/New_York', weekday: 'long',
    }).format(new Date())
    return `${weekday}, ${MONTHS[m - 1]} ${d}, ${y}`
}

function Rule({ heavy }) {
    return <div className={`fp-rule ${heavy ? 'heavy' : ''}`} />
}

// A drawn "i", so it recolours and never renders as a different glyph.
function InfoMark() {
    return (
        <svg width="15" height="15" viewBox="0 0 16 16" aria-hidden="true">
            <circle cx="8" cy="8" r="7" fill="none" stroke="currentColor" strokeWidth="1.3" />
            <circle cx="8" cy="4.6" r="0.9" fill="currentColor" />
            <path d="M8 7 L8 11.6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
    )
}

export function HowToPlayNote({ onClose }) {
    return (
        <div className="fp-note-overlay" onClick={onClose}>
            <div className="fp-note" onClick={e => e.stopPropagation()} role="dialog" aria-label="How to play">
                <button className="fp-note-close" onClick={onClose} aria-label="Close">✕</button>
                <span className="fp-kicker">The rules, briefly</span>
                <h3 className="fp-note-title">How to play</h3>
                <p className="fp-note-body">
                    You are given a player. Name every club he turned out for, <em>in the order he
                    played for them</em>. Three wrong clubs and the career is revealed.
                </p>
                <VerdictKey />
            </div>
        </div>
    )
}

function StartScreen({
    on_start_daily,
    on_start_unlimited,
    daily_done,
    day_number,
    quota = null,
    quota_gone = false,
    billing = null,
    buying = false,
    on_buy = null,
    on_open_archive = null,
    resumable = null,
    on_resume = null,
    standings = null,
    record = null,
    archive_count = null,
}) {
    const [note, setNote] = useState(false)

    const remaining = quota?.remaining
    const out_of_games = quota_gone || remaining === 0
    const can_buy = Boolean(billing?.available) && !billing?.owned && Boolean(on_buy)

    return (
        <div className="front-page">
            <header className="fp-masthead">
                <div className="fp-masthead-line">
                    <span className="fp-issue">No. {day_number}</span>
                    <span className="fp-issue">{issueDate()}</span>
                </div>
                <Rule heavy />
                <h1 className="fp-title">The Journeyman Register</h1>
                <Rule />
                <p className="fp-strap">A career, one club at a time</p>
            </header>

            {resumable && on_resume && (
                <div className="fp-standfirst">
                    <button className="resume-btn" onClick={on_resume}>
                        Resume your {resumable === 'daily' ? 'daily' : resumable === 'archive' ? 'archive' : 'game'}
                    </button>
                    <span className="resume-note">The clock kept running.</span>
                </div>
            )}

            <div className="fp-columns">
                {/* Lead column: what there is to play today. */}
                <section className="fp-col fp-lead">
                    <span className="fp-kicker">The lead</span>
                    <Rule heavy />

                    <article className="fp-entry">
                        <h2 className="fp-entry-title">Daily Journey No. {day_number}</h2>
                        <p className="fp-entry-body">
                            {daily_done
                                ? 'Filed for today. A new career is set overnight.'
                                : 'One career, one attempt, the same for everybody.'}
                        </p>
                        <button
                            className="fp-play"
                            onClick={on_start_daily}
                            disabled={daily_done}
                        >
                            {daily_done ? 'Filed ✓' : 'Play today'}
                        </button>
                    </article>

                    <Rule />

                    <article className="fp-entry">
                        <h2 className="fp-entry-title">Unlimited</h2>
                        <p className="fp-entry-body">
                            {out_of_games
                                ? 'That is today’s free run. The daily is always free, and more come tomorrow.'
                                : remaining != null
                                    ? `${remaining} free ${remaining === 1 ? 'journey' : 'journeys'} left today.`
                                    : 'Careers drawn at random, as many as you like.'}
                        </p>
                        <button className="fp-play" onClick={on_start_unlimited} disabled={out_of_games}>
                            Play a career
                        </button>
                        {out_of_games && can_buy && (
                            <button className="upgrade-btn" onClick={on_buy} disabled={buying}>
                                {buying ? 'Opening checkout…' : 'Unlock unlimited'}
                            </button>
                        )}
                    </article>
                </section>

                {/* Standings column: today's board, then your own record. */}
                <aside className="fp-col fp-aside">
                    <span className="fp-kicker">Today&rsquo;s standing</span>
                    <Rule heavy />

                    {standings === null && <p className="fp-quiet">Loading…</p>}

                    {standings && standings.length === 0 && (
                        <p className="fp-quiet">Nobody has filed today. Go first.</p>
                    )}

                    {standings && standings.length > 0 && (
                        <ol className="fp-standings">
                            {standings.slice(0, 5).map((row, i) => (
                                <li key={row.id} className="fp-standing">
                                    <span className="fp-standing-rank">{i + 1}</span>
                                    <span className="fp-standing-name">{row.display_name}</span>
                                    <span className="fp-standing-score">{(row.score ?? 0).toLocaleString()}</span>
                                </li>
                            ))}
                        </ol>
                    )}

                    {record && (
                        <>
                            <Rule />
                            <span className="fp-kicker">Your record</span>
                            <dl className="fp-record">
                                <div><dt>Played</dt><dd>{record.played}</dd></div>
                                <div><dt>Won</dt><dd>{record.wins}</dd></div>
                                <div><dt>Streak</dt><dd>{record.streak}</dd></div>
                            </dl>
                        </>
                    )}
                </aside>
            </div>

            <Rule heavy />

            <footer className="fp-foot">
                {on_open_archive && (
                    <button className="fp-foot-link" onClick={on_open_archive}>
                        The archive
                        {archive_count ? <span className="fp-foot-count"> · {archive_count} back {archive_count === 1 ? 'number' : 'numbers'}</span> : null}
                    </button>
                )}
                <button className="fp-foot-link fp-info" onClick={() => setNote(true)} aria-label="How to play">
                    <InfoMark />
                    How to play
                </button>
            </footer>

            {note && <HowToPlayNote onClose={() => setNote(false)} />}
        </div>
    )
}

export { InfoMark }
export default StartScreen
