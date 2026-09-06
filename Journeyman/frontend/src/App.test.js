import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// The regression this guards: with REACT_APP_SUPABASE_* unset, lib/supabase
// threw at import time. index.js imports App imports lib/supabase, so React
// never mounted and the deploy served a blank page -- for a game whose only
// hard dependency is /api.
//
// Rendering App with the variables unset is the only honest test of that: it
// exercises the real import chain rather than asserting about a mock.

beforeAll(() => {
    delete process.env.REACT_APP_SUPABASE_URL
    delete process.env.REACT_APP_SUPABASE_ANON_KEY
    jest.spyOn(console, 'warn').mockImplementation(() => {})
})

beforeEach(() => {
    localStorage.clear()
    global.fetch = jest.fn(() =>
        Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({}),
        })
    )
})

afterAll(() => jest.restoreAllMocks())

test('the game renders with Supabase unconfigured', async () => {
    // eslint-disable-next-line global-require
    const App = require('./App').default
    render(<App />)

    // The start screen is present, which is the whole claim: the app mounted
    // and the game is playable without any Supabase configuration at all.
    await screen.findByText(/Daily Journey/)
    expect(screen.getByText('Unlimited')).toBeInTheDocument()
})

test('the account panel says what is unavailable instead of offering a dead form', async () => {
    // eslint-disable-next-line global-require
    const App = require('./App').default
    render(<App />)

    await userEvent.click(await screen.findByText('Account'))

    expect(screen.getByText(/Accounts are unavailable/i)).toBeInTheDocument()
    // The sign-in form would submit to a client that does not exist.
    expect(screen.queryByPlaceholderText(/password/i)).not.toBeInTheDocument()
})

describe('picking up a game that was in progress', () => {
    const ACTIVE_KEY = 'journeyman_active_session'

    function serve(session, { status = 200 } = {}) {
        global.fetch = jest.fn(() =>
            Promise.resolve({
                ok: status < 400,
                status,
                json: () => Promise.resolve(session),
            })
        )
    }

    const in_progress = {
        session_id: 'abc-123',
        player: 'Bob Lanier',
        num_teams: 2,
        results: ['green', null],
        guesses: ['Detroit Pistons', null],
        wrong_guesses: 0,
        max_wrong_guesses: 3,
        status: 'active',
        elapsed_seconds: 42,
    }

    test('a stored session is restored from the server, not from localStorage', async () => {
        localStorage.setItem(ACTIVE_KEY, JSON.stringify({ session_id: 'abc-123', mode: 'daily' }))
        serve(in_progress)

        // eslint-disable-next-line global-require
        const App = require('./App').default
        render(<App />)

        await screen.findByText('Bob Lanier')
        // The stored id is a handle; every field rendered came from the response.
        expect(global.fetch.mock.calls[0][0]).toContain('/api/game/abc-123')
    })

    test('a session the server no longer has clears the key and shows the start screen', async () => {
        localStorage.setItem(ACTIVE_KEY, JSON.stringify({ session_id: 'gone', mode: 'daily' }))
        serve({ error: 'no such session' }, { status: 404 })

        // eslint-disable-next-line global-require
        const App = require('./App').default
        render(<App />)

        await waitFor(() => expect(localStorage.getItem(ACTIVE_KEY)).toBeNull())
        expect(screen.getByText(/Daily Journey/)).toBeInTheDocument()
    })

    test('a finished session is not resumed', async () => {
        localStorage.setItem(ACTIVE_KEY, JSON.stringify({ session_id: 'done', mode: 'daily' }))
        serve({ ...in_progress, status: 'won' })

        // eslint-disable-next-line global-require
        const App = require('./App').default
        render(<App />)

        await waitFor(() => expect(localStorage.getItem(ACTIVE_KEY)).toBeNull())
        expect(screen.getByText(/Daily Journey/)).toBeInTheDocument()
    })
})
