import { supabase } from './supabase'

// Client for the session API.
//
// Every call carries the Supabase access token when one exists, because the
// server reads the player's identity from that token rather than from anything
// in the request body. Playing signed out is fine -- the request simply goes
// without a token and the session has no owner.
//
// Nothing here ever receives the answer while a game is in progress. `teams`
// appears in a response only once the game is over.

export class ApiError extends Error {
    constructor(message, status) {
        super(message)
        this.name = 'ApiError'
        this.status = status
    }

    // The daily has already been played by this account today. A distinct
    // check because it is an ordinary outcome, not a failure.
    get is_already_played() {
        return this.status === 409
    }
}

async function auth_headers() {
    try {
        const { data: { session } } = await supabase.auth.getSession()
        if (session?.access_token) {
            return { Authorization: `Bearer ${session.access_token}` }
        }
    } catch {
        // Treat an unreadable session as signed out rather than failing the
        // request: anonymous play must keep working when auth is unavailable.
    }
    return {}
}

async function request(path, { method = 'GET', body } = {}) {
    let response
    try {
        response = await fetch(path, {
            method,
            headers: {
                'Content-Type': 'application/json',
                ...(await auth_headers()),
            },
            body: body === undefined ? undefined : JSON.stringify(body),
        })
    } catch (cause) {
        throw new ApiError('Could not reach the server. Check your connection.', 0)
    }

    let payload = {}
    try {
        payload = await response.json()
    } catch {
        // A non-JSON body means something upstream failed before reaching the
        // app -- a proxy error page, say. The status is what matters.
    }

    if (!response.ok) {
        throw new ApiError(payload.error || 'Something went wrong.', response.status)
    }

    return payload
}

export function start_game({ mode = 'unlimited', hard_mode = false, exclude = [] } = {}) {
    return request('/api/game/start', {
        method: 'POST',
        body: { mode, hard_mode, exclude },
    })
}

export function get_game(session_id) {
    return request(`/api/game/${session_id}`)
}

export function submit_guess(session_id, position, guess) {
    return request(`/api/game/${session_id}/guess`, {
        method: 'POST',
        body: { position, guess },
    })
}

export function use_hint(session_id) {
    return request(`/api/game/${session_id}/hint`, { method: 'POST' })
}

export function set_hard_mode(session_id, enabled) {
    return request(`/api/game/${session_id}/hard-mode`, {
        method: 'POST',
        body: { enabled },
    })
}

export function abandon_game(session_id) {
    return request(`/api/game/${session_id}/abandon`, { method: 'POST' })
}
