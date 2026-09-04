import {
    calculate_streaks,
    score_breakdown,
    BASE,
    TIME_GRACE,
    HINT_PEN,
    WRONG_PEN,
    SCORE_FLOOR,
    HARD_MULTIPLIER,
} from './scoring'

// Scoring moved to the server, so what is tested here is display maths only:
// the streak counts the Stats tab derives, and the penalty breakdown rendered
// beside the score the server sent. backend/tests/test_scoring.py owns the
// scoring rules themselves.

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

    test('the breakdown reconciles with the scores the server actually returns', () => {
        // ScoreBreakdown in game.js renders these parts and applies the floor
        // and multiplier itself, beside a score the server computed. If the two
        // drift, players see a breakdown that does not add up.
        //
        // The scoring rules live in Python now, so this checks against the same
        // frozen baseline backend/tests/test_scoring.py uses -- the only place
        // that cross-language agreement can still be asserted.
        const baseline = require('../../../backend/tests/fixtures/scoring_parity.json')

        for (const { input, expected } of baseline.score) {
            if (input.result !== 'win') continue

            const { base, time_pen, hint_pen, wrong_pen } = score_breakdown(input)
            const floored = Math.max(SCORE_FLOOR, base - time_pen - hint_pen - wrong_pen)
            const rendered = input.hard_mode ? Math.round(floored * HARD_MULTIPLIER) : floored

            expect(rendered).toBe(expected)
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
