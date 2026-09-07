import { useEffect, useState } from 'react'

// A rubber stamp pressed onto the page.
//
// The old win animation was confetti, in the pre-redesign gold and green, and
// the loss was a red flash with falling ash. Both are screen effects — they
// belong to a game that glows. This is a record book, and a record book does
// not throw confetti at you. It stamps the entry and moves on.
//
// The press is the whole effect: it arrives large and faint, lands hard and
// slightly askew, and settles. Askew because a stamp pressed by hand never
// lands square, and that tiny wrongness is what makes it read as pressed rather
// than drawn.

function prefersReducedMotion() {
    try {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches
    } catch {
        return false
    }
}

function Stamp({ label, sublabel, tone = 'ink', tilt = -7, active = true }) {
    const [pressed, setPressed] = useState(false)
    const still = prefersReducedMotion()

    useEffect(() => {
        if (!active) return undefined
        if (still) { setPressed(true); return undefined }
        // One frame late, so the transition has a state to move from.
        const id = requestAnimationFrame(() => setPressed(true))
        return () => cancelAnimationFrame(id)
    }, [active, still])

    if (!active) return null

    return (
        <div
            className={`stamp stamp-${tone} ${pressed ? 'pressed' : ''} ${still ? 'still' : ''}`}
            style={{ '--stamp-tilt': `${tilt}deg` }}
            aria-hidden="true"
        >
            <span className="stamp-rule" />
            <span className="stamp-label">{label}</span>
            {sublabel && <span className="stamp-sublabel">{sublabel}</span>}
            <span className="stamp-rule" />
        </div>
    )
}

export default Stamp
