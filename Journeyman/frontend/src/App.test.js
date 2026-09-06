import { render, screen } from '@testing-library/react'
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

