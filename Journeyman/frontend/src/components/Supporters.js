import { useEffect, useState } from 'react'

// The people who paid, named on the front page.
//
// A fade rather than a scrolling ticker. A ticker reads as broadcast — a
// crawl along the bottom of a sports channel — and this is meant to read as
// print. A masthead credits its backers in a line that sits still long enough
// to be read.
//
// Published by default, per the owner's decision. What makes that fair rather
// than merely legal is that the person can turn it off from their own account
// and is told before they pay, not after — see the Account tab and the Full
// Access panel.

const ROTATE_MS = 4200
const NAMES_SHOWN = 3

// Somebody who has asked their system not to animate should not be made to
// watch names fade. They get the first few, held still.
function prefersReducedMotion() {
    try {
        return window.matchMedia('(prefers-reduced-motion: reduce)').matches
    } catch {
        return false
    }
}

function Supporters({ names = [], count = 0 }) {
    const [offset, setOffset] = useState(0)
    const [fading, setFading] = useState(false)
    const still = prefersReducedMotion()

    const rotates = !still && names.length > NAMES_SHOWN

    useEffect(() => {
        if (!rotates) return undefined

        const timer = setInterval(() => {
            // Fade out, swap, fade in — rather than a cross-dissolve, which at
            // this size just looks like the text is broken.
            setFading(true)
            setTimeout(() => {
                setOffset(o => (o + NAMES_SHOWN) % names.length)
                setFading(false)
            }, 420)
        }, ROTATE_MS)

        return () => clearInterval(timer)
    }, [rotates, names.length])

    // Nothing to show yet. Deliberately renders nothing rather than an empty
    // frame with a heading — a strip captioned "Supporters" above a blank line
    // reads as broken, not as new.
    if (names.length === 0 && count === 0) return null

    const shown = []
    for (let i = 0; i < Math.min(NAMES_SHOWN, names.length); i++) {
        shown.push(names[(offset + i) % names.length])
    }

    // The count includes people who opted out of being named, so it can exceed
    // what is listed. Saying "and N others" from that difference would be
    // announcing the existence of people who asked not to be announced.
    const unnamed = Math.max(0, count - names.length)

    return (
        <div className="supporters">
            <span className="supporters-kicker">
                {count === 1 ? 'Supported by' : `Supported by ${count} readers`}
            </span>
            {names.length > 0 && (
                <span className={`supporters-names ${fading ? 'fading' : ''}`}>
                    {shown.join(' · ')}
                </span>
            )}
            {names.length === 0 && unnamed > 0 && (
                <span className="supporters-names">Thank you.</span>
            )}
        </div>
    )
}

export default Supporters
