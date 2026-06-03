export const BASE        = 1000
export const TIME_GRACE  = 30   // free seconds before penalty starts
export const TIME_RATE   = 1    // points lost per second after grace
export const HINT_PEN    = 150  // penalty for using the hint
export const WRONG_PEN   = 100  // penalty per wrong guess
export const SCORE_FLOOR = 100  // minimum score for any win

export function calculate_score({ result, time_seconds, wrong_guesses, hint_used }) {
    if (result !== 'win') return 0
    const time_pen  = Math.max(0, time_seconds - TIME_GRACE) * TIME_RATE
    const hint_pen  = hint_used  ? HINT_PEN  : 0
    const wrong_pen = wrong_guesses * WRONG_PEN
    return Math.max(SCORE_FLOOR, BASE - time_pen - hint_pen - wrong_pen)
}

export function score_breakdown({ time_seconds, wrong_guesses, hint_used }) {
    return {
        base:        BASE,
        time_pen:    Math.max(0, time_seconds - TIME_GRACE) * TIME_RATE,
        hint_pen:    hint_used  ? HINT_PEN  : 0,
        wrong_pen:   wrong_guesses * WRONG_PEN,
    }
}
