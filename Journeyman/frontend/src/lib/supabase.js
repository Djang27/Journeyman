import { createClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.REACT_APP_SUPABASE_URL
const supabaseAnonKey = process.env.REACT_APP_SUPABASE_ANON_KEY

// Fail at import time rather than on the first query. The old behaviour --
// console.error, then createClient(undefined, undefined) anyway -- turned a
// misconfigured build into a confusing error much later, somewhere unrelated.
//
// Note this fires in the browser at startup, not during `npm run build`: CRA
// inlines these values while bundling but never executes the module, so a build
// with missing vars still succeeds and fails on first load. That is loud enough
// to catch a mis-scoped Vercel variable on a preview deploy, which is the case
// this is guarding.
//
// It does mean a missing variable takes the whole app down rather than just the
// signed-in features. Degrading to anonymous play instead belongs with the rest
// of the fallback work in Phase 2 (ops/degraded-mode), where every call site
// gets guarded together.
const missing = [
    !supabaseUrl && 'REACT_APP_SUPABASE_URL',
    !supabaseAnonKey && 'REACT_APP_SUPABASE_ANON_KEY',
].filter(Boolean)

if (missing.length > 0) {
    throw new Error(
        `Missing environment ${missing.length === 1 ? 'variable' : 'variables'}: ${missing.join(', ')}. ` +
        'Copy frontend/.env.example to frontend/.env.local and fill in the values ' +
        'from your Supabase project, or set them for this environment in Vercel.'
    )
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
