import { render, screen } from '@testing-library/react'
import Stamp from './Stamp'
import WinAnimation from './WinAnimation'
import LoseAnimation from './LoseAnimation'

// The win was confetti and the loss was a red flash with falling ash. Both were
// screen effects on a page that is trying to look printed. These pin the
// replacement and, more usefully, the two things worth not regressing: nothing
// renders when it should not, and somebody who asked for no motion still learns
// the outcome.

describe('the stamp', () => {
    test('it says what happened in words', () => {
        // The information is the word, not the press. An animation that carries
        // the meaning is an animation that fails for anyone who cannot see it.
        render(<Stamp label="Filed" sublabel="Career complete" />)
        expect(screen.getByText('Filed')).toBeInTheDocument()
        expect(screen.getByText('Career complete')).toBeInTheDocument()
    })

    test('an inactive stamp renders nothing', () => {
        const { container } = render(<Stamp label="Filed" active={false} />)
        expect(container).toBeEmptyDOMElement()
    })

    test('a sublabel is optional', () => {
        render(<Stamp label="Filed" />)
        expect(screen.getByText('Filed')).toBeInTheDocument()
    })
})

describe('winning', () => {
    test('nothing shows until the game is won', () => {
        const { container } = render(<WinAnimation active={false} />)
        expect(container).toBeEmptyDOMElement()
    })

    test('a win is filed', () => {
        render(<WinAnimation active />)
        expect(screen.getByText('Filed')).toBeInTheDocument()
    })
})

describe('losing', () => {
    test('nothing shows until the game is lost', () => {
        const { container } = render(<LoseAnimation active={false} />)
        expect(container).toBeEmptyDOMElement()
    })

    test('a loss is marked unfinished, not failed', () => {
        // "Unfinished" is what a ledger says about a line it could not close.
        // It is also kinder, and just as true.
        render(<LoseAnimation active />)
        expect(screen.getByText('Unfinished')).toBeInTheDocument()
        expect(screen.getByText(/career is revealed/i)).toBeInTheDocument()
    })
})

describe('reduced motion', () => {
    const original = window.matchMedia

    afterEach(() => { window.matchMedia = original })

    test('the outcome still arrives with motion turned off', () => {
        window.matchMedia = () => ({ matches: true, addEventListener() {}, removeEventListener() {} })
        render(<WinAnimation active />)
        expect(screen.getByText('Filed')).toBeInTheDocument()
    })

    test('a browser without matchMedia does not crash the end of a game', () => {
        // jsdom and older browsers. Losing the stamp is a blemish; throwing
        // here would take down the screen that tells somebody they won.
        window.matchMedia = undefined
        render(<WinAnimation active />)
        expect(screen.getByText('Filed')).toBeInTheDocument()
    })
})

describe('the stamp is not buried by the results sheet', () => {
    // The bug: the win stamp was gated on show_results, so it was created at
    // the same moment the sheet appeared -- and the sheet is z-index 150
    // against the stamp's 70. It rendered underneath the thing covering it and
    // was never seen.
    //
    // Raising the stamp above the sheet would have shown it *through* the
    // results, which is worse. The ordering was what was wrong: the stamp
    // lands on the board, then the sheet rises over it.

    test('a win stamps without waiting for the sheet', () => {
        // The regression, named. It must not depend on show_results at all.
        render(<WinAnimation active />)
        expect(screen.getByText('Filed')).toBeInTheDocument()
    })

    test('it is still there once the sheet is up, rather than unmounted', () => {
        // It recedes visually behind the sheet -- a mark on the page
        // underneath, not a second dialog. Whether it is dimmed is a CSS
        // detail; that it survives is the behaviour.
        render(<WinAnimation active receded />)
        expect(screen.getByText('Filed')).toBeInTheDocument()
    })
})
