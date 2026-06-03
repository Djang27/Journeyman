import { useEffect } from 'react'
import confetti from 'canvas-confetti'

const GOLD  = '#f5c518'
const GREEN = '#538d4e'
const WHITE = '#ffffff'

function burst(origin, angle) {
    confetti({
        particleCount: 60,
        angle,
        spread: 70,
        origin,
        colors: [GOLD, GREEN, WHITE],
        scalar: 1.1,
        gravity: 0.9,
    })
}

function WinAnimation({ active }) {
    useEffect(() => {
        if (!active) return

        // Opening double-burst from both sides
        burst({ x: 0, y: 0.6 }, 60)
        burst({ x: 1, y: 0.6 }, 120)

        // Sustained shower for 3 seconds
        const end = Date.now() + 3000
        let frame

        const shower = () => {
            confetti({
                particleCount: 4,
                angle: 60,
                spread: 55,
                origin: { x: 0, y: 0.5 },
                colors: [GOLD, GREEN, WHITE],
                gravity: 1,
            })
            confetti({
                particleCount: 4,
                angle: 120,
                spread: 55,
                origin: { x: 1, y: 0.5 },
                colors: [GOLD, GREEN, WHITE],
                gravity: 1,
            })
            if (Date.now() < end) {
                frame = requestAnimationFrame(shower)
            }
        }

        shower()
        return () => cancelAnimationFrame(frame)
    }, [active])

    return null
}

export default WinAnimation
