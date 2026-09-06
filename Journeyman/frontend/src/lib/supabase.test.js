// A missing REACT_APP_SUPABASE_* variable used to throw at import time. Because
// index.js -> App.js -> this module is a direct chain, that threw before React
// mounted: a mis-scoped Vercel variable turned the whole game into a blank white
// page, including the parts that never touch Supabase.
//
// These tests pin the replacement behaviour: degrade, do not throw.

const REAL_ENV = process.env

function load_with(env) {
    jest.resetModules()
    process.env = { ...REAL_ENV, ...env }
    // eslint-disable-next-line global-require
    return require('./supabase')
}

afterEach(() => {
    process.env = REAL_ENV
    jest.restoreAllMocks()
})

describe('when Supabase is not configured', () => {
    const unset = {
        REACT_APP_SUPABASE_URL: undefined,
        REACT_APP_SUPABASE_ANON_KEY: undefined,
    }

    test('importing does not throw', () => {
        jest.spyOn(console, 'warn').mockImplementation(() => {})
        expect(() => load_with(unset)).not.toThrow()
    })

    test('the client is null and auth reports itself unavailable', () => {
        jest.spyOn(console, 'warn').mockImplementation(() => {})
        const mod = load_with(unset)
        expect(mod.supabase).toBeNull()
        expect(mod.authAvailable).toBe(false)
    })

    test('it names every missing variable, so the deploy can be fixed', () => {
        const warn = jest.spyOn(console, 'warn').mockImplementation(() => {})
        load_with(unset)
        expect(warn).toHaveBeenCalledTimes(1)
        expect(warn.mock.calls[0][0]).toContain('REACT_APP_SUPABASE_URL')
        expect(warn.mock.calls[0][0]).toContain('REACT_APP_SUPABASE_ANON_KEY')
    })

    test('a half-configured build is treated as unconfigured', () => {
        jest.spyOn(console, 'warn').mockImplementation(() => {})
        const mod = load_with({
            REACT_APP_SUPABASE_URL: 'https://example.supabase.co',
            REACT_APP_SUPABASE_ANON_KEY: undefined,
        })
        expect(mod.authAvailable).toBe(false)
        expect(mod.missingSupabaseConfig).toEqual(['REACT_APP_SUPABASE_ANON_KEY'])
    })
})

describe('when Supabase is configured', () => {
    test('a real client is created and nothing is warned about', () => {
        const warn = jest.spyOn(console, 'warn').mockImplementation(() => {})
        const mod = load_with({
            REACT_APP_SUPABASE_URL: 'https://example.supabase.co',
            REACT_APP_SUPABASE_ANON_KEY: 'anon-key',
        })
        expect(mod.authAvailable).toBe(true)
        expect(mod.supabase).not.toBeNull()
        expect(mod.missingSupabaseConfig).toEqual([])
        expect(warn).not.toHaveBeenCalled()
    })
})
