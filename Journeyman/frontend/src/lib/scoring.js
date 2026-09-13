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
export const TIME_GRACE       = 30    // free seconds, when the length is unknown
// Free seconds, scaled to the work. A flat grace charges a nine-stop career
// for the seven extra names it has to type, which is mechanics rather than
// thinking. Mirrors scoring.py; the two must agree or the breakdown shown
// beside a score stops explaining that score.
export const BASE_TIME_GRACE      = 15
export const TIME_GRACE_PER_TEAM  = 10

export function time_grace(team_count) {
    if (!team_count) return TIME_GRACE
    return BASE_TIME_GRACE + TIME_GRACE_PER_TEAM * team_count
}
export const TIME_RATE        = 1     // points lost per second after grace
// The clock keeps running while somebody is away -- it runs on the server, and
// a browser that could discount its own time could claim a perfect one. What is
// bounded is the damage: time can take 600 of the 1000, reached at 10.5
// minutes. A long clean game still scores 400 rather than the floor.
export const MAX_TIME_PENALTY = 600
export const HINT_PEN         = 150   // penalty for using the hint
export const WRONG_PEN        = 100   // penalty per wrong guess
// A misplacement is not a wrong answer -- right team, wrong slot -- so it costs
// no life. It costs points, because a free yellow would let anyone who knows
// the teams permute them until everything turned green, and the order is the
// game.
export const MISPLACED_PEN    = 25    // penalty per right-team-wrong-slot guess
export const SCORE_FLOOR      = 100   // minimum score for any win
export const HARD_MULTIPLIER  = 1.5   // score multiplier for hard mode wins

export function score_breakdown({ time_seconds, wrong_guesses, hint_used, hard_mode, misplaced_guesses = 0, team_count = null }) {
    return {
        base:        BASE,
        time_pen:    Math.min(Math.max(0, time_seconds - time_grace(team_count)) * TIME_RATE, MAX_TIME_PENALTY),
        hint_pen:    hint_used ? HINT_PEN  : 0,
        wrong_pen:   wrong_guesses * WRONG_PEN,
        misplaced_pen: misplaced_guesses * MISPLACED_PEN,
        hard_mode:   !!hard_mode,
    }
}
