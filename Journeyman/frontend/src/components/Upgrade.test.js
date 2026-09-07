import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Upgrade, { UpgradeMark } from './Upgrade'

// The corner mark and the sheet it opens. What matters is that somebody who
// already paid is never sold to again, and that a deployment without Stripe
// shows no buy button rather than a broken one.

const noop = () => {}
const free = { available: true, owned: false, signed_in: true, free_games_per_day: 5 }

function sheet(billing, props = {}) {
    render(<Upgrade billing={billing} on_close={noop} {...props} />)
}

describe('the corner mark', () => {
    test('it opens the sheet', async () => {
        const onClick = jest.fn()
        render(<UpgradeMark owned={false} onClick={onClick} />)
        await userEvent.click(screen.getByRole('button'))
        expect(onClick).toHaveBeenCalled()
    })

    test('an owner gets a receipt, not an advert', () => {
        render(<UpgradeMark owned onClick={noop} />)
        expect(screen.getByLabelText(/Your subscription/i)).toBeInTheDocument()
    })

    test('a non-owner is offered the description', () => {
        render(<UpgradeMark owned={false} onClick={noop} />)
        expect(screen.getByLabelText(/What the full register includes/i)).toBeInTheDocument()
    })
})

describe('what the sheet says', () => {
    test('it lists what you get', () => {
        sheet(free)
        expect(screen.getByText(/Unlimited journeys/i)).toBeInTheDocument()
        expect(screen.getByText(/The full archive/i)).toBeInTheDocument()
        expect(screen.getByText(/Whatever comes next/i)).toBeInTheDocument()
    })

    test('it promises the daily stays free', () => {
        // The funnel. Anyone reading the offer should see the free thing is
        // not what is being taken away.
        sheet(free)
        expect(screen.getByText(/daily puzzle is free forever/i)).toBeInTheDocument()
    })

    test('it says the free allowance out loud', () => {
        sheet(free)
        expect(screen.getByText(/5 journeys a day/i)).toBeInTheDocument()
    })

    test('it says plainly that it does not renew', () => {
        // A one-time price people expect to renew is a support email a month.
        sheet(free)
        expect(screen.getByText(/does not renew/i)).toBeInTheDocument()
    })
})

describe('who sees a buy button', () => {
    test('a signed-in free player does', () => {
        sheet(free, { on_buy: noop })
        expect(screen.getByText(/One payment, kept for good/i)).toBeInTheDocument()
    })

    test('clicking it starts checkout', async () => {
        const on_buy = jest.fn()
        sheet(free, { on_buy })
        await userEvent.click(screen.getByText(/One payment, kept for good/i))
        expect(on_buy).toHaveBeenCalled()
    })

    test('it disables itself while checkout opens', () => {
        sheet(free, { on_buy: noop, buying: true })
        expect(screen.getByText(/Opening checkout/i)).toBeDisabled()
    })

    test('a signed-out visitor is told to sign in first', () => {
        sheet({ ...free, signed_in: false }, { on_buy: noop })
        expect(screen.getByText(/Sign in first/i)).toBeInTheDocument()
        expect(screen.queryByText(/One payment/i)).not.toBeInTheDocument()
    })

    test('an unconfigured deployment shows no buy button', () => {
        sheet({ ...free, available: false }, { on_buy: noop })
        expect(screen.queryByText(/One payment/i)).not.toBeInTheDocument()
        expect(screen.getByText(/Not on sale just yet/i)).toBeInTheDocument()
    })

    test('an owner is thanked, not sold to', () => {
        sheet({ ...free, owned: true }, { on_buy: noop })
        expect(screen.getByText(/You have the full register/i)).toBeInTheDocument()
        expect(screen.queryByText(/One payment/i)).not.toBeInTheDocument()
        expect(screen.queryByText(/does not renew/i)).not.toBeInTheDocument()
    })
})
