import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY

// A missing variable used to throw here, at import time. That was loud, which
// was the point -- but index.js imports App.js imports this, so the throw
// happened before React mounted and the whole game became a blank white page.
// A mis-scoped Vercel variable took down the part of the app that does not need
// Supabase at all: the game itself, which talks only to /api.
//
// So: degrade instead. `supabase` is null when unconfigured, `authAvailable`
// says so out loud, and the sign-in UI hides itself. Anonymous play works. The
// console warning is still there for whoever is debugging the deploy.
export const missingSupabaseConfig = [
    !supabaseUrl && 'REACT_APP_SUPABASE_URL',
    !supabaseAnonKey && 'REACT_APP_SUPABASE_ANON_KEY',
].filter(Boolean)

export const authAvailable = missingSupabaseConfig.length === 0

if (!authAvailable) {
    // eslint-disable-next-line no-console
    console.warn(
        `Journeyman: missing ${missingSupabaseConfig.join(', ')}. ` +
        'Accounts, history and the leaderboard are disabled; the game still plays. ' +
        'Copy frontend/.env.example to frontend/.env.local, or set these for this ' +
        'environment in Vercel.'
    )
}

export const supabase = authAvailable ? createClient(supabaseUrl, supabaseAnonKey) : null
