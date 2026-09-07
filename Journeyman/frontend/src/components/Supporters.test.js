import { render, screen, act } from '@testing-library/react'
import Supporters from './Supporters'

// Published by default, per the owner's decision. These pin the parts that
// make that fair rather than merely permitted — and the one that would be a
// genuine breach: naming, by arithmetic, somebody who asked not to be named.

describe('when nobody has bought yet', () => {
    test('it renders nothing at all', () => {
        // A strip captioned "Supported by" above a blank line reads as broken,
        // not as new.
        const { container } = render(<Supporters names={[]} count={0} />)
        expect(container).toBeEmptyDOMElement()
    })
})

describe('naming supporters', () => {
    test('names are shown', () => {
        render(<Supporters names={['Ada', 'Grace']} count={2} />)
        expect(screen.getByText(/Ada · Grace/)).toBeInTheDocument()
    })

    test('the count is the honest total', () => {
        render(<Supporters names={['Ada', 'Grace']} count={2} />)
        expect(screen.getByText(/Supported by 2 readers/i)).toBeInTheDocument()
    })

    test('a single supporter is not called "1 readers"', () => {
        render(<Supporters names={['Ada']} count={1} />)
        expect(screen.getByText('Supported by')).toBeInTheDocument()
    })
})

describe('somebody who opted out', () => {
    test('their name never appears', () => {
        // The server filters them out; this is the second line of defence.
        render(<Supporters names={['Ada']} count={4} />)
        expect(screen.queryByText(/Grace/)).not.toBeInTheDocument()
    })

    test('the count still includes them', () => {
        // Opting out removes a name from the strip, not a person from the
        // total. A count that quietly shrank would misreport how many paid.
        render(<Supporters names={['Ada']} count={4} />)
        expect(screen.getByText(/Supported by 4 readers/i)).toBeInTheDocument()
    })

    test('their existence is never announced as "and N others"', () => {
        // This is the one that would actually breach the opt-out: telling
        // everybody that three people supported the game and asked not to be
        // named is naming them by arithmetic.
        render(<Supporters names={['Ada']} count={4} />)
        expect(screen.queryByText(/others/i)).not.toBeInTheDocument()
        expect(screen.queryByText(/3/)).not.toBeInTheDocument()
    })

    test('all of them opting out leaves a thank-you, not a blank', () => {
        render(<Supporters names={[]} count={3} />)
        expect(screen.getByText('Thank you.')).toBeInTheDocument()
        expect(screen.queryByText(/others/i)).not.toBeInTheDocument()
    })
})

describe('the rotation', () => {
    beforeEach(() => jest.useFakeTimers())
    afterEach(() => jest.useRealTimers())

    test('a short list does not rotate', () => {
        render(<Supporters names={['Ada', 'Grace']} count={2} />)
        act(() => { jest.advanceTimersByTime(20000) })
        expect(screen.getByText(/Ada · Grace/)).toBeInTheDocument()
    })

    test('a long list moves on', () => {
        const names = ['Ada', 'Grace', 'Alan', 'Edsger', 'Barbara', 'Donald']
        render(<Supporters names={names} count={6} />)
        expect(screen.getByText(/Ada · Grace · Alan/)).toBeInTheDocument()

        act(() => { jest.advanceTimersByTime(4200) })
        act(() => { jest.advanceTimersByTime(500) })

        expect(screen.getByText(/Edsger · Barbara · Donald/)).toBeInTheDocument()
    })
})
