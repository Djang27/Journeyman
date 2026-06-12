import { useEffect, useRef } from 'react'
import confetti from 'canvas-confetti'

const GOLD  = '#f5c518'
const GREEN = '#538d4e'
const WHITE = '#ffffff'

function WinAnimation({ active }) {
    const canvasRef = useRef(null)

    useEffect(() => {
        if (!active || !canvasRef.current) return

        const fire = confetti.create(canvasRef.current, { resize: true })

        fire({ particleCount: 60, angle: 60,  spread: 70, origin: { x: 0, y: 0.6 }, colors: [GOLD, GREEN, WHITE], scalar: 1.1, gravity: 0.9 })
        fire({ particleCount: 60, angle: 120, spread: 70, origin: { x: 1, y: 0.6 }, colors: [GOLD, GREEN, WHITE], scalar: 1.1, gravity: 0.9 })

        const end = Date.now() + 3000
        let frame

        const shower = () => {
            fire({ particleCount: 4, angle: 60,  spread: 55, origin: { x: 0, y: 0.5 }, colors: [GOLD, GREEN, WHITE], gravity: 1 })
            fire({ particleCount: 4, angle: 120, spread: 55, origin: { x: 1, y: 0.5 }, colors: [GOLD, GREEN, WHITE], gravity: 1 })
            if (Date.now() < end) frame = requestAnimationFrame(shower)
        }

        shower()
        return () => cancelAnimationFrame(frame)
    }, [active])

    return (
        <canvas
            ref={canvasRef}
            style={{
                position: 'fixed',
                inset: 0,
                width: '100%',
                height: '100%',
                pointerEvents: 'none',
                zIndex: 999,
            }}
        />
    )
}

export default WinAnimation
