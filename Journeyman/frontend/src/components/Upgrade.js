// The offer, kept out of the way until somebody asks what it is.
//
// Called Full Access rather than anything register-flavoured: the almanac is a
// visual language, not a rename. The game is Journeyman.
//
// A corner mark rather than a banner: this is a game, and a permanent sales
// strip across the top of one is how a free game starts feeling like a trial.
// It says what you get, in the register's own voice, and nothing about it
// changes what a free player can do today.

const BENEFITS = [
    {
        title: 'Unlimited journeys',
        body: 'Play as many careers as you like, every day. The daily puzzle stays free for everyone, always.',
    },
    {
        title: 'The full archive',
        body: 'Every daily since launch, back to the first one, playable in your own time.',
    },
    {
        title: 'Whatever comes next',
        body: 'New modes and features land here first, and are included — the price does not change when they do.',
    },
]

// A drawn seal rather than an icon font or an emoji: it scales, it recolours,
// and it looks printed rather than pasted on.
function Seal({ size = 20, filled = false }) {
    return (
        <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="10.5" fill={filled ? '#8c3a24' : 'none'} stroke="#8c3a24" strokeWidth="1.4" />
            <path
                d="M12 6.2 L13.7 10.2 L18 10.6 L14.8 13.4 L15.7 17.6 L12 15.4 L8.3 17.6 L9.2 13.4 L6 10.6 L10.3 10.2 Z"
                fill={filled ? '#efe7d6' : '#8c3a24'}
            />
        </svg>
    )
}

export function UpgradeMark({ owned, onClick }) {
    // Owners keep a quiet mark: it is a receipt, not an advertisement.
    return (
        <button
            className={`upgrade-mark ${owned ? 'owned' : ''}`}
            onClick={onClick}
            aria-label={owned ? 'Your full access' : 'What full access includes'}
            title={owned ? 'Full access' : 'What you get'}
        >
            <Seal filled={owned} />
            <span className="upgrade-mark-label">Full access</span>
        </button>
    )
}

function Upgrade({ billing, buying, on_buy, on_close }) {
    const owned = Boolean(billing?.owned)
    const available = Boolean(billing?.available)
    const signed_in = Boolean(billing?.signed_in)
    const free_per_day = billing?.free_games_per_day ?? 5

    return (
        <div className="upgrade-overlay" onClick={on_close}>
            <div className="upgrade-sheet" onClick={e => e.stopPropagation()} role="dialog" aria-label="Full access">
                <button className="upgrade-close" onClick={on_close} aria-label="Close">✕</button>

                <div className="upgrade-masthead">
                    <span className="upgrade-kicker">One-time unlock</span>
                    <h2 className="upgrade-title">Full Access</h2>
                </div>

                <p className="upgrade-lede">
                    {owned
                        ? 'You have full access. Thank you — it is what keeps this going.'
                        : `The daily puzzle is free forever and always will be. Beyond it, ${free_per_day} journeys a day are on the house.`}
                </p>

                <ul className="upgrade-list">
                    {BENEFITS.map(benefit => (
                        <li key={benefit.title} className="upgrade-item">
                            <span className="upgrade-item-mark"><Seal size={14} filled={owned} /></span>
                            <div>
                                <span className="upgrade-item-title">{benefit.title}</span>
                                <span className="upgrade-item-body">{benefit.body}</span>
                            </div>
                        </li>
                    ))}
                </ul>

                {!owned && (
                    <div className="upgrade-foot">
                        {available && signed_in && on_buy && (
                            <button className="upgrade-buy" onClick={on_buy} disabled={buying}>
                                {buying ? 'Opening checkout…' : 'One payment, kept for good'}
                            </button>
                        )}
                        {available && !signed_in && (
                            <p className="upgrade-note">Sign in first, so the purchase stays with your account.</p>
                        )}
                        {!available && (
                            <p className="upgrade-note">Not on sale just yet — check back shortly.</p>
                        )}
                        {/* Said plainly. A one-time price that people expect to
                            renew is a support email every month. */}
                        <p className="upgrade-fine">Paid once. Not a subscription, and it does not renew.</p>
                        {/* Before the money moves, not after. An opt-out
                            somebody learns about by seeing their own name is
                            not much of one. */}
                        <p className="upgrade-fine">
                            Supporters are named on the front page. You can turn that off any
                            time in your account.
                        </p>
                    </div>
                )}
            </div>
        </div>
    )
}

export default Upgrade
