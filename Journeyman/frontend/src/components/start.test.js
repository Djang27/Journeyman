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
        expect(screen.getByText('Play a career')).toBeEnabled()
    })
})

describe('while games remain', () => {
    test('it counts down', () => {
        show({ quota: { remaining: 3, limit: 5 } })
        expect(screen.getByText(/3 free journeys left today/i)).toBeInTheDocument()
    })

    test('the last one is singular', () => {
        show({ quota: { remaining: 1, limit: 5 } })
        expect(screen.getByText(/1 free journey left today/i)).toBeInTheDocument()
    })

    test('unlimited is still playable', () => {
        show({ quota: { remaining: 1, limit: 5 } })
        expect(screen.getByText('Play a career')).toBeEnabled()
    })
})

describe('once they are gone', () => {
    test('unlimited is disabled', () => {
        show({ quota: { remaining: 0, limit: 5 } })
        expect(screen.getByText('Play a career')).toBeDisabled()
    })

    test('it points at what is still free rather than only what is not', () => {
        show({ quota_gone: true })
        expect(screen.getByText(/daily is always free/i)).toBeInTheDocument()
        expect(screen.getByText(/tomorrow/i)).toBeInTheDocument()
    })

    test('the daily is never blocked by the unlimited quota', () => {
        show({ quota_gone: true })
        expect(screen.getByText('Play today')).toBeEnabled()
    })

    test('a refusal with no quota body still disables unlimited', () => {
        // quota_gone alone must be enough -- the server always sends the block,
        // but the UI should not depend on it to stop offering a game that fails.
        show({ quota_gone: true, quota: null })
        expect(screen.getByText('Play a career')).toBeDisabled()
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

    test('an owner is not offered the upgrade on the front page', () => {
        // The receipt lives on the corner mark now -- see Upgrade.test.
        show({ billing: { ...available, owned: true }, quota_gone: true, on_buy: () => {} })
        expect(screen.queryByText(/Unlock unlimited/i)).not.toBeInTheDocument()
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

describe('resuming a game left behind', () => {
    // Leaving a game is not abandoning it. The daily and the archive are one
    // attempt each, and an unlimited game has already cost a free game, so the
    // start screen has to offer the way back.

    test('nothing is offered when there is no game in progress', () => {
        show({ resumable: null, on_resume: () => {} })
        expect(screen.queryByText(/Resume/i)).not.toBeInTheDocument()
    })

    test('a daily in progress is offered back by name', () => {
        show({ resumable: 'daily', on_resume: () => {} })
        expect(screen.getByText(/Resume your daily/i)).toBeInTheDocument()
    })

    test('an archive game in progress is named too', () => {
        show({ resumable: 'archive', on_resume: () => {} })
        expect(screen.getByText(/Resume your archive/i)).toBeInTheDocument()
    })

    test('an unlimited game is offered back generically', () => {
        show({ resumable: 'unlimited', on_resume: () => {} })
        expect(screen.getByText(/Resume your game/i)).toBeInTheDocument()
    })

    test('it says the clock kept running', () => {
        // The score is timed server-side. A player who assumed leaving paused
        // it would find the score disagreed with them.
        show({ resumable: 'daily', on_resume: () => {} })
        expect(screen.getByText(/clock kept running/i)).toBeInTheDocument()
    })

    test('clicking it resumes', async () => {
        const on_resume = jest.fn()
        show({ resumable: 'daily', on_resume })
        await userEvent.click(screen.getByText(/Resume your daily/i))
        expect(on_resume).toHaveBeenCalled()
    })

    test('the daily and unlimited buttons are still there', () => {
        // Resuming is offered, not forced.
        show({ resumable: 'daily', on_resume: () => {} })
        expect(screen.getByText(/Daily Journey No\./)).toBeInTheDocument()
        expect(screen.getByText('Unlimited')).toBeInTheDocument()
    })
})

describe('the front page', () => {
    // It was a logo and two buttons on an empty field. A front page carries the
    // things somebody wants before they start: what today's puzzle is, who is
    // ahead, how they have done, and what else there is to read.

    test('the masthead carries the issue number', () => {
        show({ day_number: 88 })
        expect(screen.getByText('No. 88')).toBeInTheDocument()
    })

    test('today’s standing is shown', () => {
        show({
            standings: [
                { id: 'a', display_name: 'Quick', score: 900 },
                { id: 'b', display_name: 'Steady', score: 880 },
            ],
        })
        expect(screen.getByText('Quick')).toBeInTheDocument()
        expect(screen.getByText('900')).toBeInTheDocument()
    })

    test('an empty board invites you to go first rather than looking broken', () => {
        show({ standings: [] })
        expect(screen.getByText(/Go first/i)).toBeInTheDocument()
    })

    test('a board still loading says so', () => {
        show({ standings: null })
        expect(screen.getByText(/Loading/i)).toBeInTheDocument()
    })

    test('the standing never shows more than five', () => {
        const many = Array.from({ length: 12 }, (_, i) => ({
            id: `u${i}`, display_name: `Player ${i}`, score: 900 - i,
        }))
        show({ standings: many })
        expect(screen.getByText('Player 0')).toBeInTheDocument()
        expect(screen.queryByText('Player 6')).not.toBeInTheDocument()
    })

    test('your own record appears when there is one', () => {
        show({ record: { played: 12, wins: 9, streak: 3 } })
        expect(screen.getByText('Played')).toBeInTheDocument()
        expect(screen.getByText('12')).toBeInTheDocument()
    })

    test('no record section for a signed-out visitor', () => {
        show({ record: null })
        expect(screen.queryByText('Played')).not.toBeInTheDocument()
    })

    test('the archive says how much is in it', () => {
        show({ on_open_archive: () => {}, archive_count: 3 })
        expect(screen.getByText(/3 back numbers/i)).toBeInTheDocument()
    })

    test('one back number is singular', () => {
        show({ on_open_archive: () => {}, archive_count: 1 })
        expect(screen.getByText(/1 back number$/i)).toBeInTheDocument()
    })
})

describe('the rules, reachable from the front page', () => {
    // Burying how to play in a sidebar tab means the people who most need it
    // never open it.

    test('an info button opens them', async () => {
        show({})
        await userEvent.click(screen.getByLabelText(/How to play/i))
        expect(screen.getByText(/in the order he/i)).toBeInTheDocument()
    })

    test('the note explains all three marks', async () => {
        show({})
        await userEvent.click(screen.getByLabelText(/How to play/i))
        expect(screen.getByText('Correct')).toBeInTheDocument()
        expect(screen.getByText('Wrong stop')).toBeInTheDocument()
        expect(screen.getByText('Never played there')).toBeInTheDocument()
    })

    test('it closes', async () => {
        show({})
        await userEvent.click(screen.getByLabelText(/How to play/i))
        await userEvent.click(screen.getByLabelText('Close'))
        expect(screen.queryByText(/in the order he/i)).not.toBeInTheDocument()
    })
})

describe('the colophon', () => {
    // Where a paper puts this. Small and present rather than three clicks deep:
    // somebody looking for it is looking for a reason to trust the thing.

    test('the NBA disclaimer is on the page itself, not only behind a link', () => {
        show({})
        expect(screen.getByText(/Not affiliated with the NBA/i)).toBeInTheDocument()
    })

    test('privacy opens and says what is kept', async () => {
        show({})
        await userEvent.click(screen.getByText('Privacy'))
        expect(screen.getByText(/no advertising, no third-party/i)).toBeInTheDocument()
    })

    test('privacy is honest about anonymous play', async () => {
        // The claim has to match the code: rate_limit keeps 16 hex characters
        // of a SHA-256 and never the address.
        show({})
        await userEvent.click(screen.getByText('Privacy'))
        expect(screen.getByText(/never written down/i)).toBeInTheDocument()
    })

    test('privacy says card details never reach us', async () => {
        show({})
        await userEvent.click(screen.getByText('Privacy'))
        expect(screen.getByText(/never reach Journeyman/i)).toBeInTheDocument()
    })

    test('attribution disclaims affiliation and names the source', async () => {
        show({})
        await userEvent.click(screen.getByText('About the data'))
        expect(screen.getByText(/not affiliated with, endorsed by/i)).toBeInTheDocument()
        expect(screen.getByText(/Basketball-Reference/i)).toBeInTheDocument()
    })

    test('a sheet closes', async () => {
        show({})
        await userEvent.click(screen.getByText('Privacy'))
        await userEvent.click(screen.getByLabelText('Close'))
        expect(screen.queryByText(/no advertising/i)).not.toBeInTheDocument()
    })

    test('only one sheet is open at a time', async () => {
        show({})
        await userEvent.click(screen.getByText('Privacy'))
        await userEvent.click(screen.getByLabelText('Close'))
        await userEvent.click(screen.getByText('About the data'))
        expect(screen.queryByText(/no advertising/i)).not.toBeInTheDocument()
        expect(screen.getByText(/Basketball-Reference/i)).toBeInTheDocument()
    })
})
