// Privacy and attribution, written from what the code actually does.
//
// Every claim below was checked against the source rather than copied from a
// template: a privacy policy that describes collection you do not do is as
// wrong as one that omits collection you do, and the second kind is the one
// that gets you in trouble.
//
// What the app actually stores, as of this writing:
//   auth.users        email and a password hash, via Supabase GoTrue
//   profiles          a display name
//   game_sessions     the game state, with the answer, per attempt
//   game_results      score, time, mode, result
//   entitlements      what was bought, and from which payment
//   payment_events    the provider's event, verbatim
//   rate_limit_counters  a salted hash prefix of an address, never the address
//   game_quota        the same hash prefix, for the free allowance
//
// Not stored anywhere: card details (Stripe holds those), and IP addresses in
// any recoverable form -- rate_limit.hash_client_address keeps 16 hex
// characters of a SHA-256 and discards the rest.

const UPDATED = 'September 2026'

function Section({ title, children }) {
    return (
        <section className="legal-section">
            <h3 className="legal-heading">{title}</h3>
            {children}
        </section>
    )
}

export function PrivacyPolicy() {
    return (
        <div className="legal">
            <p className="legal-updated">Last updated {UPDATED}</p>

            <Section title="The short version">
                <p>
                    Journeyman stores what it needs to run a puzzle game with accounts and a
                    leaderboard, and nothing else. There is no advertising, no third-party
                    tracking, and nothing is sold or shared with anybody.
                </p>
            </Section>

            <Section title="If you play without an account">
                <p>
                    Nothing identifying is stored. Games are kept on the server while they are
                    being played, and they are not attached to a person. To keep one visitor from
                    using the whole free allowance, a short one-way hash of your network address
                    is counted against — sixteen characters of a SHA-256, which is enough to tell
                    two visitors apart and not enough to identify either. The address itself is
                    never written down.
                </p>
            </Section>

            <Section title="If you make an account">
                <p>
                    Your email address and a password hash, held by Supabase, which provides the
                    database and sign-in. A display name, which you choose and can change, and
                    which is shown on the leaderboard. And your games: the score, time, mode and
                    result of each one.
                </p>
            </Section>

            <Section title="If you buy Full Access">
                <p>
                    Payment is handled by Stripe. Card details go to Stripe and never reach
                    Journeyman&rsquo;s servers. What is stored here is that a purchase happened,
                    which payment it came from, and the events Stripe sent about it — kept
                    because a refund or a dispute has to be traceable to the payment it concerns.
                </p>
            </Section>

            <Section title="Analytics">
                <p>
                    Page views and referrers, through Vercel Web Analytics. It is cookieless and
                    aggregate: it counts visits and where they arrived from, and does not build a
                    profile of anybody or follow them to other sites.
                </p>
                <p>
                    Errors are reported to Sentry so faults can be fixed. Request bodies are not
                    sent, which is a setting rather than a hope — see{' '}
                    <code>send_default_pii=False</code> in the source.
                </p>
            </Section>

            <Section title="Cookies">
                <p>
                    One, set by Supabase to keep you signed in. Nothing for advertising or
                    tracking. Some preferences — an unfinished game, whether you played today —
                    are kept in your browser&rsquo;s local storage and never leave it.
                </p>
            </Section>

            <Section title="What you can ask for">
                <p>
                    A copy of your data, a correction, or deletion of your account and everything
                    attached to it. Deleting an account removes your profile, results and
                    entitlement; anonymous game records that were never attached to you are not
                    affected because there is nothing to attach them to.
                </p>
                <p>Ask by email and it will be done.</p>
            </Section>

            <Section title="Changes">
                <p>
                    If what is collected changes, this page changes with it and the date above
                    moves.
                </p>
            </Section>
        </div>
    )
}

export function Attribution() {
    return (
        <div className="legal">
            <Section title="Not affiliated with the NBA">
                <p>
                    Journeyman is an independent project. It is not affiliated with, endorsed by,
                    sponsored by, or connected to the National Basketball Association, its teams,
                    or any of its players.
                </p>
                <p>
                    Team and player names are used to describe real careers, which is what the
                    game is about. All trademarks belong to their owners. No team logos, marks or
                    likenesses are used.
                </p>
            </Section>

            <Section title="Where the data comes from">
                <p>
                    Career histories are built from a public dataset derived from
                    Basketball-Reference, released into the public domain. Journeyman claims no
                    ownership of the underlying facts — a list of the clubs a player turned out
                    for is a matter of record, not a creative work.
                </p>
                <p>
                    Mistakes are possible. Careers that cannot be ordered confidently are held
                    out of rotation rather than guessed at, but if you spot one that is wrong,
                    say so and it will be fixed.
                </p>
            </Section>
        </div>
    )
}

export default PrivacyPolicy
