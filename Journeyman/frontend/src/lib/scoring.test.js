import {
    calculate_score,
    calculate_streaks,
    score_breakdown,
    BASE,
    TIME_GRACE,
    HINT_PEN,
    WRONG_PEN,
    SCORE_FLOOR,
    HARD_MULTIPLIER,
} from './scoring'

// A clean win: inside the time grace, no hint, no wrong guesses.
const perfect = { result: 'win', time_seconds: 10, wrong_guesses: 0, hint_used: false, hard_mode: false }

describe('calculate_score', () => {
    test('a loss always scores zero', () => {
        expect(calculate_score({ ...perfect, result: 'loss' })).toBe(0)
        expect(calculate_score({ ...perfect, result: 'loss', time_seconds: 1 })).toBe(0)
    })

    test('a perfect win inside the grace period scores the full base', () => {
        expect(calculate_score(perfect)).toBe(BASE)
    })

    test('no time penalty accrues up to the grace boundary', () => {
        expect(calculate_score({ ...perfect, time_seconds: TIME_GRACE })).toBe(BASE)
    })

    test('time is charged per second past the grace period', () => {
        expect(calculate_score({ ...perfect, time_seconds: TIME_GRACE + 40 })).toBe(BASE - 40)
    })

    test('the hint is charged once regardless of timing', () => {
        expect(calculate_score({ ...perfect, hint_used: true })).toBe(BASE - HINT_PEN)
    })

    test('wrong guesses are charged per guess', () => {
        expect(calculate_score({ ...perfect, wrong_guesses: 2 })).toBe(BASE - 2 * WRONG_PEN)
    })

    test('penalties stack', () => {
        const score = calculate_score({
            ...perfect,
            time_seconds: TIME_GRACE + 100,
            wrong_guesses: 1,
            hint_used: true,
        })
        expect(score).toBe(BASE - 100 - WRONG_PEN - HINT_PEN)
    })

    test('a slow win never drops below the floor', () => {
        expect(calculate_score({ ...perfect, time_seconds: 10_000 })).toBe(SCORE_FLOOR)
    })

    test('hard mode multiplies the win', () => {
        expect(calculate_score({ ...perfect, hard_mode: true })).toBe(BASE * HARD_MULTIPLIER)
    })

    test('hard mode multiplies after the floor is applied, not before', () => {
        // The floor is a floor on the pre-multiplier score, so the lowest
        // possible hard-mode win is 150 rather than 100. Pinned because moving
        // the multiplier inside the Math.max would silently change every score.
        const score = calculate_score({ ...perfect, time_seconds: 10_000, hard_mode: true })
        expect(score).toBe(Math.round(SCORE_FLOOR * HARD_MULTIPLIER))
    })

    test('hard mode does not rescue a loss', () => {
        expect(calculate_score({ ...perfect, result: 'loss', hard_mode: true })).toBe(0)
    })

    test('scores are always integers', () => {
        for (const time_seconds of [0, 31, 77, 450]) {
            for (const hard_mode of [false, true]) {
                const score = calculate_score({ ...perfect, time_seconds, hard_mode })
                expect(Number.isInteger(score)).toBe(true)
            }
        }
    })
})

describe('score_breakdown', () => {
    test('reports each penalty separately', () => {
        expect(
            score_breakdown({
                time_seconds: TIME_GRACE + 25,
                wrong_guesses: 2,
                hint_used: true,
                hard_mode: false,
            })
        ).toEqual({
            base: BASE,
            time_pen: 25,
            hint_pen: HINT_PEN,
            wrong_pen: 2 * WRONG_PEN,
            hard_mode: false,
        })
    })

    test('reconciles with calculate_score once the floor and multiplier are applied', () => {
        // ScoreBreakdown in game.js renders these parts and applies the floor
        // and multiplier itself. If the two functions ever drift, players see a
        // breakdown that does not add up to the score beside it.
        const cases = [
            { time_seconds: 5, wrong_guesses: 0, hint_used: false, hard_mode: false },
            { time_seconds: 120, wrong_guesses: 2, hint_used: true, hard_mode: false },
            { time_seconds: 10_000, wrong_guesses: 2, hint_used: true, hard_mode: false },
            { time_seconds: 60, wrong_guesses: 0, hint_used: false, hard_mode: true },
            { time_seconds: 10_000, wrong_guesses: 0, hint_used: true, hard_mode: true },
        ]

        for (const params of cases) {
            const { base, time_pen, hint_pen, wrong_pen } = score_breakdown(params)
            const floored = Math.max(SCORE_FLOOR, base - time_pen - hint_pen - wrong_pen)
            const expected = params.hard_mode ? Math.round(floored * HARD_MULTIPLIER) : floored

            expect(calculate_score({ ...params, result: 'win' })).toBe(expected)
        }
    })
})

describe('calculate_streaks', () => {
    // Sidebar passes rows straight from Supabase, which returns newest first.
    const win = { result: 'win' }
    const loss = { result: 'loss' }

    test('an empty history has no streaks', () => {
        expect(calculate_streaks([])).toEqual({ current: 0, best: 0 })
    })

    test('counts the current streak from the most recent game', () => {
        expect(calculate_streaks([win, win, loss, win]).current).toBe(2)
    })

    test('a loss in the most recent game ends the current streak', () => {
        expect(calculate_streaks([loss, win, win, win]).current).toBe(0)
    })

    test('finds the best streak anywhere in the history', () => {
        expect(calculate_streaks([win, loss, win, win, win, loss]).best).toBe(3)
    })

    test('the current streak counts toward the best streak', () => {
        expect(calculate_streaks([win, win, win, loss, win])).toEqual({ current: 3, best: 3 })
    })

    test('an all-loss history has no streaks', () => {
        expect(calculate_streaks([loss, loss])).toEqual({ current: 0, best: 0 })
    })

    test('an all-win history streaks the whole way', () => {
        expect(calculate_streaks([win, win, win, win])).toEqual({ current: 4, best: 4 })
    })
})
