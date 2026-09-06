import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Archive from './Archive'

// The rule worth testing here is the one that is easy to break later: a puzzle
// you have not played must never show its player, because that is the answer.
// The server withholds it, and this asserts the UI cannot reintroduce it.

const noop = () => {}

const unplayed = { puzzle_date: '2026-09-05', day_number: 87, played: false, player: null, num_teams: 3 }
const played   = { puzzle_date: '2026-09-04', day_number: 86, played: true,  player: 'Bob Lanier', num_teams: 2 }

function show(archive, props = {}) {
    render(<Archive archive={archive} on_play={noop} on_close={noop} {...props} />)
}

describe('when the archive is locked', () => {
    const locked = { puzzles: [unplayed], unlocked: false, signed_in: true }

    test('the puzzles are listed anyway', () => {
        // Seeing what is in there is the argument for buying it.
        show(locked)
        expect(screen.getByText('Daily #87')).toBeInTheDocument()
    })

    test('playing is disabled', () => {
        show(locked)
        expect(screen.getByText('Locked')).toBeDisabled()
    })

    test('the offer is shown', () => {
        show(locked, { on_buy: noop })
        expect(screen.getByText(/Unlock the archive/i)).toBeInTheDocument()
    })
})

describe('when the archive is unlocked', () => {
    const open = { puzzles: [unplayed, played], unlocked: true, signed_in: true }

    test('an unplayed puzzle can be played', () => {
        show(open)
        expect(screen.getByText('Play')).toBeEnabled()
    })

    test('clicking it starts that date', async () => {
        const on_play = jest.fn()
        show(open, { on_play })
        await userEvent.click(screen.getByText('Play'))
        expect(on_play).toHaveBeenCalledWith('2026-09-05')
    })

    test('a played puzzle cannot be replayed', () => {
        // One attempt each: a replayable puzzle with a recorded score is a
        // score you grind rather than earn.
        show(open)
        expect(screen.getByText('Played ✓')).toBeDisabled()
    })

    test('the offer is not shown to somebody who already bought', () => {
        show(open, { on_buy: noop })
        expect(screen.queryByText(/Unlock the archive/i)).not.toBeInTheDocument()
    })
})

describe('answers', () => {
    test('an unplayed puzzle never shows a player', () => {
        show({ puzzles: [unplayed], unlocked: true, signed_in: true })
        expect(screen.queryByText(/Lanier/i)).not.toBeInTheDocument()
    })

    test('a played one does, because it is no longer an answer', () => {
        show({ puzzles: [played], unlocked: true, signed_in: true })
        expect(screen.getByText('Bob Lanier')).toBeInTheDocument()
    })

    test('a player smuggled onto an unplayed row is still not rendered', () => {
        // Defence in depth. The server withholds it; if a future change stopped
        // doing so, the UI should not be the thing that spoils the puzzle.
        show({
            puzzles: [{ ...unplayed, player: 'Bob Lanier' }],
            unlocked: true,
            signed_in: true,
        })
        expect(screen.queryByText(/Lanier/i)).not.toBeInTheDocument()
    })
})

describe('edge cases', () => {
    test('an empty archive says so rather than looking broken', () => {
        show({ puzzles: [], unlocked: true, signed_in: true })
        expect(screen.getByText(/check back tomorrow/i)).toBeInTheDocument()
    })

    test('a failed load does not crash the overlay', () => {
        show(null)
        expect(screen.getByText('The Archive')).toBeInTheDocument()
    })

    test('a signed-out visitor is told why nothing is ticked', () => {
        show({ puzzles: [unplayed], unlocked: false, signed_in: false })
        expect(screen.getByText(/Sign in to see which ones/i)).toBeInTheDocument()
    })
})
