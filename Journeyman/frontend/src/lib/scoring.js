// Scoring itself lives on the server (backend/scoring.py) -- the browser is
// shown a score, it does not compute one. What is left here is display maths:
// the streaks the Stats tab derives from history, and the penalty breakdown
// rendered beside the score the server sent.

// games must be ordered newest-first (as returned by Supabase)
export function calculate_streaks(games) {
    let current = 0
    let best    = 0
    let run     = 0

    for (const g of games) {
        if (g.result === 'win') current++
        else break
    }

    for (let i = games.length - 1; i >= 0; i--) {
        if (games[i].result === 'win') {
            run++
            if (run > best) best = run
        } else {
            run = 0
        }
    }

    return { current, best }
}

export const BASE             = 1000
export const TIME_GRACE       = 30    // free seconds before penalty starts
export const TIME_RATE        = 1     // points lost per second after grace
export const HINT_PEN         = 150   // penalty for using the hint
export const WRONG_PEN        = 100   // penalty per wrong guess
export const SCORE_FLOOR      = 100   // minimum score for any win
export const HARD_MULTIPLIER  = 1.5   // score multiplier for hard mode wins

export function score_breakdown({ time_seconds, wrong_guesses, hint_used, hard_mode }) {
    return {
        base:        BASE,
        time_pen:    Math.max(0, time_seconds - TIME_GRACE) * TIME_RATE,
        hint_pen:    hint_used ? HINT_PEN  : 0,
        wrong_pen:   wrong_guesses * WRONG_PEN,
        hard_mode:   !!hard_mode,
    }
}
