import { render, screen } from '@testing-library/react'
import Verdict, { VerdictKey, VERDICTS } from './verdict'

// The redesign's first pass signalled state with colour alone, in a muted
// palette where the green and the ochre were hard to tell apart and the "wrong"
// colour was the accent's own hex. These pin the fix: every state says itself
// in words, so the meaning survives a colour-blind reader, a greyscale
// screenshot, and a palette change.

describe('every state says itself in words', () => {
    test('correct', () => {
        render(<Verdict result="green" />)
        expect(screen.getByText('Correct')).toBeInTheDocument()
    })

    test('right club, wrong stop', () => {
        render(<Verdict result="yellow" />)
        expect(screen.getByText('Wrong stop')).toBeInTheDocument()
    })

    test('never played there', () => {
        render(<Verdict result="gray" />)
        expect(screen.getByText('Never played there')).toBeInTheDocument()
    })

    test('an ungraded stop says nothing', () => {
        const { container } = render(<Verdict result={null} />)
        expect(container).toBeEmptyDOMElement()
    })
})

describe('the labels are distinguishable', () => {
    test('no two states share a label', () => {
        // Two states reading the same is the failure this replaced, in a
        // different form.
        const labels = Object.values(VERDICTS).map(v => v.label)
        expect(new Set(labels).size).toBe(labels.length)
    })

    test('none of them is only a colour name', () => {
        // "Yellow" tells somebody nothing about what to do next, and tells a
        // colour-blind reader nothing at all.
        const labels = Object.values(VERDICTS).map(v => v.label.toLowerCase())
        for (const colour of ['green', 'yellow', 'red', 'grey', 'gray']) {
            expect(labels).not.toContain(colour)
        }
    })
})

describe('the key', () => {
    test('it explains all three', () => {
        render(<VerdictKey />)
        expect(screen.getByText('Correct')).toBeInTheDocument()
        expect(screen.getByText('Wrong stop')).toBeInTheDocument()
        expect(screen.getByText('Never played there')).toBeInTheDocument()
    })

    test('it says what a wrong stop actually means', () => {
        render(<VerdictKey />)
        expect(screen.getByText(/not at this point in the career/i)).toBeInTheDocument()
    })
})

describe('the marks are drawn, not typed', () => {
    test('each state renders an svg rather than a glyph', () => {
        // An emoji renders as a different picture on every platform and none of
        // them look printed.
        for (const result of ['green', 'yellow', 'gray']) {
            const { container } = render(<Verdict result={result} />)
            expect(container.querySelector('svg')).toBeInTheDocument()
        }
    })
})
