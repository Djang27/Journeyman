import { VerdictKey } from './verdict'

function HowToPlay({ open, onClose }) {
    return (
        <>
            <div className={`info-backdrop ${open ? 'open' : ''}`} onClick={onClose} />

            <div className={`info-panel ${open ? 'open' : ''}`}>
                <button className="info-close" onClick={onClose} aria-label="Close">✕</button>

                <h2 className="info-title">How to Play</h2>

                <div className="info-section">
                    <p className="info-lead">
                        You're given an NBA player's name. Guess every team they played for, in the correct order, to complete their journey.
                    </p>
                </div>

                <div className="info-section">
                    <p className="info-heading">Each Stop = One Team</p>
                    <p className="info-body">Each numbered stop on the road is one team in the player's career. Fill them all correctly to win.</p>

                    <div className="info-roadmap">
                        <div className="info-mini-spine" />
                        <div className="info-road-stop">
                            <div className="info-marker correct">1</div>
                            <div className="info-card-mini correct">
                                <span>Los Angeles Lakers</span>
                                <span className="info-badge correct">✓ Correct stop</span>
                            </div>
                        </div>
                        <div className="info-road-stop">
                            <div className="info-marker close">2</div>
                            <div className="info-card-mini close">
                                <span>Chicago Bulls</span>
                                <span className="info-badge close">↔ Wrong stop</span>
                            </div>
                        </div>
                        <div className="info-road-stop">
                            <div className="info-marker wrong">3</div>
                            <div className="info-card-mini wrong">
                                <span>Boston Celtics</span>
                                <span className="info-badge wrong">✗ Not in career</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="info-section">
                    <p className="info-heading">Reading a stop</p>
                    {/* The key, so the marks are learnable. Colour is
                        reinforcement here, not the message -- the mark and the
                        rule under an entry each say the state on their own. */}
                    <VerdictKey />
                </div>

                <div className="info-section">
                    <p className="info-heading">Lives</p>
                    <div className="info-lives-row">
                        <span className="life-dot remaining" />
                        <span className="life-dot remaining" />
                        <span className="life-dot remaining" />
                        <span className="info-lives-label">3 chances</span>
                    </div>
                    <p className="info-body">
                        Only a club he <strong>never played for</strong> costs a life. Naming the right club at the wrong stop costs a few points instead — it is a clue worth having. Lose all 3 and the career is revealed.
                    </p>
                </div>

                <div className="info-section">
                    <p className="info-heading">Tips</p>
                    <ul className="info-tips">
                        <li>Type a city <em>("Los Angeles")</em> or nickname <em>("Lakers")</em> to search teams</li>
                        <li>Use yellow clues — the team exists, just at a different stop</li>
                        <li>Arrow keys navigate suggestions, Enter to select</li>
                    </ul>
                </div>
            </div>
        </>
    )
}

export default HowToPlay
