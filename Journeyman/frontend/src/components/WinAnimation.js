import Stamp from './Stamp'

// A finished career gets stamped, not celebrated with confetti.
//
// This was canvas-confetti in #f5c518 and #538d4e — the pre-redesign gold and
// green, fired from both corners for three seconds. Confetti is the default
// celebration for anything on a screen, which is exactly why it does not belong
// on a page that is trying not to look like everything else.
//
// The dependency went with it.

function WinAnimation({ active }) {
    if (!active) return null

    return (
        <div className="stamp-stage" aria-hidden="true">
            <Stamp label="Filed" sublabel="Career complete" tone="correct" tilt={-8} />
        </div>
    )
}

export default WinAnimation
