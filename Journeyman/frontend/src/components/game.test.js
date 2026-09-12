import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import GameScreen from './game'

// The results sheet is the moment somebody most wants their score to mean
// something, and until now it offered them nothing to do about it.
//
// The constraint these pin down is honesty rather than layout. An anonymous
// session carries no user id, game_results.user_id is not nullable, and
// sessions.py drops the row rather than inventing an owner -- so the game just
// played is already gone by the time this renders. Copy promising to keep it
// would be a promise the server refuses to honour.

const noop = () => {}

// The sheet is deliberately delayed so the stamp lands first, so every query
// here has to wait past STAMP_HOLD_MS rather than assert immediately.
const AFTER_STAMP = { timeout: 4000 }

function play(props = {}) {
    render(
        <GameScreen
            player="Test Journeyman"
            num_teams={3}
            teams={['boston celtics', 'miami heat', 'utah jazz']}
            hints={[]}
            guesses={['boston celtics', 'miami heat', 'utah jazz']}
            results={['green', 'green', 'green']}
            on_guess_change={noop}
            on_submit={noop}
            on_clear={noop}
            has_won={true}
            has_lost={false}
            wrong_guesses={0}
            misplaced_guesses={0}
            max_guesses={3}
            hint_active={false}
            on_hint={noop}
            hard_mode={false}
            on_hard_mode_toggle={noop}
            elapsed={42}
            final_time={42}
            final_score={900}
            on_play_again={noop}
            game_mode="daily"
            day_number={1}
            {...props}
        />
    )
}

describe('offering an account when a game ends', () => {
    test('a signed-out player is offered one after a win', async () => {
        play({ signed_in: false, on_sign_in: noop })
        expect(
            await screen.findByRole('button', { name: /sign in or create an account/i }, AFTER_STAMP)
        ).toBeInTheDocument()
    })

    test('and after a loss', async () => {
        play({
            signed_in: false,
            on_sign_in: noop,
            has_won: false,
            has_lost: true,
            results: ['gray', 'gray', 'gray'],
            final_score: null,
        })
        expect(
            await screen.findByRole('button', { name: /sign in or create an account/i }, AFTER_STAMP)
        ).toBeInTheDocument()
    })

    test('a signed-in player is not asked', async () => {
        play({ signed_in: true, on_sign_in: noop })
        await screen.findByText(/career path/i, {}, AFTER_STAMP)
        expect(screen.queryByRole('button', { name: /sign in/i })).not.toBeInTheDocument()
    })

    test('nothing is offered when accounts are unavailable', async () => {
        play({ signed_in: false, on_sign_in: null })
        await screen.findByText(/career path/i, {}, AFTER_STAMP)
        expect(screen.queryByRole('button', { name: /sign in/i })).not.toBeInTheDocument()
    })

    test('it does not claim the finished game can be saved', async () => {
        // The constraint, as a test. An anonymous result is never written, so
        // "sign in to keep this result" would be false -- and it is the
        // obvious phrasing, which is exactly why it needs pinning.
        play({ signed_in: false, on_sign_in: noop })
        const note = await screen.findByText(/was not recorded/i, {}, AFTER_STAMP)
        expect(note).toBeInTheDocument()
        expect(screen.queryByText(/keep this (result|score|game)/i)).not.toBeInTheDocument()
        expect(screen.queryByText(/save this (result|score|game)/i)).not.toBeInTheDocument()
    })

    test('the offer reaches the handler', async () => {
        let opened = 0
        play({ signed_in: false, on_sign_in: () => { opened += 1 } })
        const button = await screen.findByRole(
            'button', { name: /sign in or create an account/i }, AFTER_STAMP
        )
        await userEvent.click(button)
        expect(opened).toBe(1)
    })

    test('it never sits between the player and the buttons they came for', async () => {
        // Share and play-again are why the sheet exists. The prompt goes after
        // them, so a signed-out player never has to read past an advert to
        // reach the thing they wanted.
        play({ signed_in: false, on_sign_in: noop })
        const share = await screen.findByRole('button', { name: /share result/i }, AFTER_STAMP)
        const prompt = screen.getByRole('button', { name: /sign in or create an account/i })
        expect(share.compareDocumentPosition(prompt) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })
})
