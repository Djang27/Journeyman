import { useMemo } from 'react'

function LoseAnimation({ active }) {
    // Stable random particles — useMemo so they don't re-randomise on re-render
    const particles = useMemo(() => (
        Array.from({ length: 28 }, (_, i) => ({
            id: i,
            left:     Math.random() * 100,
            delay:    Math.random() * 1.8,
            duration: 2.2 + Math.random() * 2,
            size:     5 + Math.random() * 9,
            drift:    (Math.random() - 0.5) * 60,
            opacity:  0.3 + Math.random() * 0.5,
        }))
    ), [])

    if (!active) return null

    return (
        <div className="lose-overlay" aria-hidden="true">
            {/* Brief red flash */}
            <div className="lose-flash" />

            {/* Falling ash particles */}
            {particles.map(p => (
                <div
                    key={p.id}
                    className="lose-particle"
                    style={{
                        left:              `${p.left}%`,
                        width:             `${p.size}px`,
                        height:            `${p.size}px`,
                        animationDelay:    `${p.delay}s`,
                        animationDuration: `${p.duration}s`,
                        '--drift':         `${p.drift}px`,
                        opacity:           p.opacity,
                    }}
                />
            ))}
        </div>
    )
}

export default LoseAnimation
