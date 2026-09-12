import { useState } from 'react'
import { VerdictKey } from './verdict'
import { PrivacyPolicy, Attribution } from './Legal'
import SupportersStrip from './Supporters'

// The front page.
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

// One sheet shape, three kinds of note: the rules, the privacy page and the
// attribution. Same furniture, so none of them needs its own chrome.
export function Note({ kicker, title, onClose, children }) {
    return (
        <div className="fp-note-overlay" onClick={onClose}>
            <div className="fp-note" onClick={e => e.stopPropagation()} role="dialog" aria-label={title}>
                <button className="fp-note-close" onClick={onClose} aria-label="Close">✕</button>
                <span className="fp-kicker">{kicker}</span>
                <h3 className="fp-note-title">{title}</h3>
                {children}
            </div>
        </div>
    )
}

export function HowToPlayNote({ onClose }) {
    return (
        <Note kicker="The rules, briefly" title="How to play" onClose={onClose}>
            <p className="fp-note-body">
                You are given a player. Name every club he turned out for, <em>in the order he
                played for them</em>. Three wrong clubs and the career is revealed.
            </p>
            <VerdictKey />
        </Note>
    )
}

// Who unlimited draws from.
//
// The pool was a uniform draw over everything promoted, and most of that is
// players a fan has never heard of. An unrecognisable name is not a hard
// puzzle -- there is nothing to reason from -- so it read as a broken game
// rather than a difficult one.
//
// Rendered as a set of tabs rather than a dropdown: there are three, the
// difference between them is the thing being chosen, and a dropdown hides two
// of the three behind a click. The note under them is the promise each makes.
function PoolPicker({ pools, pool, onChoose }) {
    if (!pools || pools.length === 0) return null
    const chosen = pools.find(p => p.id === pool) || pools[0]

    return (
        <div className="pool-picker">
            <span className="pool-kicker">Who you get</span>
            <div className="pool-tabs" role="group" aria-label="How well known the players are">
                {pools.map(option => (
                    <button
                        key={option.id}
                        type="button"
                        className={`pool-tab ${option.id === chosen.id ? 'chosen' : ''}`}
                        aria-pressed={option.id === chosen.id}
                        onClick={() => onChoose(option.id)}
                    >
                        {option.label}
                    </button>
                ))}
            </div>
            <p className="pool-note">{chosen.note}</p>
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
    supporters = null,
    pools = null,
    pool = null,
    on_choose_pool = null,
    signed_in = false,
    on_sign_in = null,
}) {
    // Which sheet is open: 'rules', 'privacy', 'attribution', or none.
    const [sheet, setSheet] = useState(null)

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
                <h1 className="fp-title">Journeyman</h1>
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
                        {on_choose_pool && (
                            <PoolPicker pools={pools} pool={pool} onChoose={on_choose_pool} />
                        )}
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

                    {/* Directly under the board somebody has just read, which
                        is the only place on this page where the reason to have
                        an account is already on screen. Phrased as what is
                        missing rather than as an instruction: nobody signs up
                        because they were told to, and the game deliberately
                        works without one. */}
                    {!signed_in && on_sign_in && (
                        <>
                            <Rule />
                            <span className="fp-kicker">Your record</span>
                            <p className="fp-signin-note">
                                Kept only while this tab is open. An account keeps your streak,
                                your history, and your name on the board above.
                            </p>
                            <button className="fp-signin" onClick={on_sign_in}>
                                Sign in or create an account
                            </button>
                            <p className="fp-signin-fine">
                                Free. The daily needs no account at all.
                            </p>
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
                <button className="fp-foot-link fp-info" onClick={() => setSheet('rules')} aria-label="How to play">
                    <InfoMark />
                    How to play
                </button>
            </footer>

            {/* Named above the colophon: it is a credit, and credits sit with
                the imprint rather than in the middle of the page. */}
            {supporters && (
                <SupportersStrip names={supporters.names} count={supporters.count} />
            )}

            {/* The colophon, where a paper puts this. Small, present, not hidden
                three clicks deep -- somebody looking for it is looking for a
                reason to trust the thing. */}
            <div className="fp-colophon">
                <button className="fp-colophon-link" onClick={() => setSheet('privacy')}>Privacy</button>
                <span className="fp-colophon-sep">·</span>
                <button className="fp-colophon-link" onClick={() => setSheet('attribution')}>About the data</button>
                <span className="fp-colophon-sep">·</span>
                <span className="fp-colophon-note">Not affiliated with the NBA</span>
            </div>

            {sheet === 'rules' && <HowToPlayNote onClose={() => setSheet(null)} />}
            {sheet === 'privacy' && (
                <Note kicker="What is kept, and what is not" title="Privacy" onClose={() => setSheet(null)}>
                    <PrivacyPolicy />
                </Note>
            )}
            {sheet === 'attribution' && (
                <Note kicker="Independent, and where the facts come from" title="About the data" onClose={() => setSheet(null)}>
                    <Attribution />
                </Note>
            )}
        </div>
    )
}

export { InfoMark }
export default StartScreen
