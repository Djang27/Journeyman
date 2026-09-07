import Stamp from './Stamp'

// An unfinished entry is struck, not set on fire.
//
// This was a red flash across the whole screen followed by twenty-eight falling
// ash particles. Cinematic, and about as far from a printed page as an effect
// can get — a ledger marks a line it could not close by striking it.
//
// The strike is drawn behind the stamp, so the two land together: the rule goes
// through the page, the stamp lands on top of it.

function LoseAnimation({ active }) {
    if (!active) return null

    return (
        <div className="stamp-stage" aria-hidden="true">
            <span className="stamp-strike" />
            <Stamp label="Unfinished" sublabel="The career is revealed" tone="wrong" tilt={6} />
        </div>
    )
}

export default LoseAnimation
