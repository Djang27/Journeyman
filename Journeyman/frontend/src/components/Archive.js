// Past dailies. The half of the unlock that is worth something -- a cap you
// cannot hit is not a product, ninety puzzles is.
//
// Shown to everybody, playable by owners. Somebody deciding whether to buy
// should be able to see how much is in there, and the server withholds the
// player's name for anything unplayed, so nothing here can spoil a puzzle.

function formatDate(iso) {
    const [y, m, d] = iso.split('-').map(Number)
    return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString(undefined, {
        timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric',
    })
}

function Archive({ archive, on_play, on_buy, on_close, buying = false, loading = false }) {
    const puzzles = archive?.puzzles ?? []
    const unlocked = Boolean(archive?.unlocked)
    const signed_in = Boolean(archive?.signed_in)

    return (
        <div className="archive-overlay" onClick={on_close}>
            <div className="archive-modal" onClick={e => e.stopPropagation()}>
                <button className="archive-close" onClick={on_close} aria-label="Close">✕</button>

                <h2 className="archive-title">The Archive</h2>
                <p className="archive-sub">
                    {puzzles.length > 0
                        ? `Every daily since launch — ${puzzles.length} to play.`
                        : 'Every daily since launch.'}
                </p>

                {!signed_in && (
                    <p className="archive-note">Sign in to see which ones you have played.</p>
                )}

                {!unlocked && signed_in && (
                    <div className="archive-locked">
                        <p>The archive is part of the unlimited unlock.</p>
                        {on_buy && (
                            <button className="upgrade-btn" onClick={on_buy} disabled={buying}>
                                {buying ? 'Opening checkout…' : 'Unlock the archive — one payment'}
                            </button>
                        )}
                    </div>
                )}

                {loading && <p className="archive-note">Loading…</p>}

                {!loading && puzzles.length === 0 && (
                    <p className="archive-note">Nothing here yet — check back tomorrow.</p>
                )}

                <ul className="archive-list">
                    {puzzles.map(p => (
                        <li key={p.puzzle_date} className={`archive-row ${p.played ? 'played' : ''}`}>
                            <div className="archive-row-main">
                                <span className="archive-day">Daily #{p.day_number}</span>
                                <span className="archive-date">{formatDate(p.puzzle_date)}</span>
                            </div>
                            {/* The player's name appears only once it is no longer
                                an answer -- the server withholds it until then. */}
                            {p.played && p.player && (
                                <span className="archive-player">{p.player}</span>
                            )}
                            <button
                                className="archive-play-btn"
                                onClick={() => on_play(p.puzzle_date)}
                                disabled={!unlocked || p.played}
                            >
                                {p.played ? 'Played ✓' : unlocked ? 'Play' : 'Locked'}
                            </button>
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    )
}

export default Archive
