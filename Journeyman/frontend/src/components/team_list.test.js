import { render, screen } from '@testing-library/react'
import TeamList from './team_list'

// The hint used to be a bare conference string and is now
// { conference, seasons }. Both shapes have to render, because a session that
// was already in flight when this deployed carries the old one, and a career
// the source could not date carries a null half.

const noop = () => {}

function board(props = {}) {
    render(
        <TeamList
            num_teams={2}
            hints={[null, null]}
            guesses={['', '']}
            results={[null, null]}
            on_guess_change={noop}
            on_submit={noop}
            on_clear={noop}
            game_over={false}
            {...props}
        />
    )
}

describe('the hint', () => {
    test('shows the conference and the seasons together', () => {
        board({ hints: [{ conference: 'East', seasons: '1995–1998' }, null] })
        expect(screen.getByText('East')).toBeInTheDocument()
        expect(screen.getByText('1995–1998')).toBeInTheDocument()
    })

    test('a career the source could not date still shows its conference', () => {
        board({ hints: [{ conference: 'West', seasons: null }, null] })
        expect(screen.getByText('West')).toBeInTheDocument()
    })

    test('a session from before the change still renders', () => {
        // The old wire shape. A game in flight at deploy time carries it, and
        // losing the hint mid-game is worse than showing less of one.
        board({ hints: ['East', null] })
        expect(screen.getByText('East')).toBeInTheDocument()
    })

    test('no hint means no badges', () => {
        board({ hints: [null, null] })
        expect(screen.queryByText('East')).not.toBeInTheDocument()
        expect(screen.queryByText('West')).not.toBeInTheDocument()
    })

    test('a solved slot shows no hint even when one was sent', () => {
        // The answer is already on screen; repeating a clue for it is noise.
        board({
            hints: [{ conference: 'East', seasons: '1995–1998' }, null],
            results: ['green', null],
            guesses: ['boston celtics', ''],
        })
        expect(screen.queryByText('1995–1998')).not.toBeInTheDocument()
    })
})
