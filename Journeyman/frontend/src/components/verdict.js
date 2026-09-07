// What a stop's result means, said in marks and words rather than colour.
//
// The first pass leaned on colour alone and did not read: the muted palette
// that suits paper is exactly the palette that makes a green and an ochre hard
// to tell apart, and one of the three was the accent's own hex. Colour is now
// reinforcement — the mark, the rule under the entry and the label each carry
// the state on their own.
//
// It is also how a printed table would have done it. A ledger settles a line
// with a double rule, flags a transposition with a dagger, and scratches a
// wrong entry rather than erasing it. None of that needs a colour to survive
// being photocopied.

export const VERDICTS = {
    green: {
        label: 'Correct',
        // What the mark means, for the legend.
        note: 'Right club, right stop. The line is settled.',
    },
    yellow: {
        label: 'Wrong stop',
        note: 'He played for them, but not at this point in the career.',
    },
    gray: {
        label: 'Never played there',
        note: 'Not on his roster at any point.',
    },
}

// Drawn, never a glyph: an emoji renders as a different picture on every
// platform and none of them look printed.
export function VerdictMark({ result, size = 11 }) {
    if (result === 'green') {
        // A settled tick.
        return (
            <svg className="stop-verdict-mark" width={size} height={size} viewBox="0 0 12 12" aria-hidden="true">
                <path d="M1.5 6.4 L4.4 9.2 L10.5 2.6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square" />
            </svg>
        )
    }
    if (result === 'yellow') {
        // A dagger: the printer's mark for "see the footnote, this is out of
        // place" — which is exactly what a right club in a wrong stop is.
        return (
            <svg className="stop-verdict-mark" width={size} height={size} viewBox="0 0 12 12" aria-hidden="true">
                <path d="M6 1 L6 11 M2.6 3.6 L9.4 3.6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="square" />
            </svg>
        )
    }
    // A scratch, the way a wrong entry is struck rather than rubbed out.
    return (
        <svg className="stop-verdict-mark" width={size} height={size} viewBox="0 0 12 12" aria-hidden="true">
            <path d="M2.2 2.2 L9.8 9.8 M9.8 2.2 L2.2 9.8" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="square" />
        </svg>
    )
}

export function Verdict({ result }) {
    const verdict = VERDICTS[result]
    if (!verdict) return null
    return (
        <span className={`stop-verdict ${result === 'green' ? 'correct' : result === 'yellow' ? 'close' : 'wrong'}`}>
            <VerdictMark result={result} />
            {verdict.label}
        </span>
    )
}

// The key, so the marks are learnable rather than guessable. Shown in How to
// Play beside the rules.
export function VerdictKey() {
    return (
        <div className="verdict-key">
            {['green', 'yellow', 'gray'].map(result => (
                <div key={result} className="verdict-key-row">
                    <span className={`verdict-key-term ${result === 'green' ? 'correct' : result === 'yellow' ? 'close' : 'wrong'}`}
                          style={{ color: `var(--${result === 'green' ? 'green-correct' : result === 'yellow' ? 'yellow-close' : 'gray-wrong'})` }}>
                        <VerdictMark result={result} size={10} />
                        {VERDICTS[result].label}
                    </span>
                    <span className="verdict-key-desc">{VERDICTS[result].note}</span>
                </div>
            ))}
        </div>
    )
}

export default Verdict
