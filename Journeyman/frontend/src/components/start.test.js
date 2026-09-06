import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import StartScreen from './start'

// The allowance is shown before it runs out, not only when it does. A cap a
// player discovers by hitting it reads as a wall; one they watch count down
// reads as the terms.
//
// The distinction these pin down is null vs 0: null means the rule does not
// apply (the daily, or a player who paid), 0 means it applies and is spent.
// Collapsing them shows "0 free games left" to someone with unlimited access.

const noop = () => {}

function show(props = {}) {
    render(
        <StartScreen
            on_start_daily={noop}
            on_start_unlimited={noop}
            daily_done={false}
            day_number={1}
            {...props}
        />
    )
}

describe('when the quota does not apply', () => {
    test('no allowance line is shown at all', () => {
        show({ quota: null })
        expect(screen.queryByText(/free game/i)).not.toBeInTheDocument()
    })

    test('unlimited stays playable', () => {
        show({ quota: null })
        expect(screen.getByText('Unlimited')).toBeEnabled()
    })
})

describe('while games remain', () => {
    test('it counts down', () => {
        show({ quota: { remaining: 3, limit: 5 } })
        expect(screen.getByText('3 free games left today')).toBeInTheDocument()
    })

    test('the last one is singular', () => {
        show({ quota: { remaining: 1, limit: 5 } })
        expect(screen.getByText('1 free game left today')).toBeInTheDocument()
    })

    test('unlimited is still playable', () => {
        show({ quota: { remaining: 1, limit: 5 } })
        expect(screen.getByText('Unlimited')).toBeEnabled()
    })
})

describe('once they are gone', () => {
    test('unlimited is disabled', () => {
        show({ quota: { remaining: 0, limit: 5 } })
        expect(screen.getByText('Unlimited')).toBeDisabled()
    })

    test('it points at what is still free rather than only what is not', () => {
        show({ quota_gone: true })
        expect(screen.getByText(/daily puzzle is always free/i)).toBeInTheDocument()
        expect(screen.getByText(/tomorrow/i)).toBeInTheDocument()
    })

    test('the daily is never blocked by the unlimited quota', () => {
        show({ quota_gone: true })
        expect(screen.getByText(/Daily Journey/)).toBeEnabled()
    })

    test('a refusal with no quota body still disables unlimited', () => {
        // quota_gone alone must be enough -- the server always sends the block,
        // but the UI should not depend on it to stop offering a game that fails.
        show({ quota_gone: true, quota: null })
        expect(screen.getByText('Unlimited')).toBeDisabled()
    })
})

describe('the upgrade offer', () => {
    const available = { available: true, owned: false, signed_in: true, free_games_per_day: 5 }

    test('is not shown while the player still has free games', () => {
        // Selling mid-session to somebody who has games left is how a generous
        // cap starts feeling like a trap.
        show({ quota: { remaining: 3, limit: 5 }, billing: available, on_buy: () => {} })
        expect(screen.queryByText(/Unlock unlimited/i)).not.toBeInTheDocument()
    })

    test('appears once they are gone', () => {
        show({ quota_gone: true, billing: available, on_buy: () => {} })
        expect(screen.getByText(/Unlock unlimited/i)).toBeInTheDocument()
    })

    test('is absent when the server says payments are unconfigured', () => {
        // A deployment without Stripe shows no buy button rather than a broken one.
        show({ quota_gone: true, billing: { available: false }, on_buy: () => {} })
        expect(screen.queryByText(/Unlock unlimited/i)).not.toBeInTheDocument()
    })

    test('is absent for someone who already bought', () => {
        show({ quota_gone: true, billing: { ...available, owned: true }, on_buy: () => {} })
        expect(screen.queryByText(/Unlock unlimited/i)).not.toBeInTheDocument()
    })

    test('an owner is told they have access rather than being sold to', () => {
        show({ billing: { ...available, owned: true } })
        expect(screen.getByText(/Unlimited access/i)).toBeInTheDocument()
    })

    test('never appears from the URL alone', () => {
        // The server decides. ?purchase=success proves nothing -- anyone can
        // visit that address.
        show({ quota_gone: true, billing: null, on_buy: () => {} })
        expect(screen.queryByText(/Unlock unlimited/i)).not.toBeInTheDocument()
    })

    test('clicking it starts checkout', async () => {
        const on_buy = jest.fn()
        show({ quota_gone: true, billing: available, on_buy })
        await userEvent.click(screen.getByText(/Unlock unlimited/i))
        expect(on_buy).toHaveBeenCalled()
    })

    test('it disables itself while checkout is opening', () => {
        show({ quota_gone: true, billing: available, on_buy: () => {}, buying: true })
        expect(screen.getByText(/Opening checkout/i)).toBeDisabled()
    })
})
