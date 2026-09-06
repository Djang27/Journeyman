"""Find payments that were made and never fulfilled, and fulfil them.

The bug this exists for raises nothing. Somebody pays, the webhook never
arrives or its handler throws, and the first anyone hears about it is an email
from a person who is annoyed and correct. Every other check in this project
would report a perfectly healthy game.

That is the same class of failure as the leaderboard that returned an empty
list for months and the daily that 500'd on a foreign key: silent, and only
findable by asking a question from outside. This asks two.

## Two questions, two sources

**What did Stripe say happened?** Recent completed Checkout sessions, compared
against what we recorded. A session Stripe considers paid that we have no event
for is a webhook that never landed -- a delivery lost, an endpoint that was down
past the retry window, or a signature secret rotated at the wrong moment.

**What did we record and fail to apply?** Events already in payment_events with
processed_at still null. Those were received but their handler threw, and a
provider redelivery will not retry them because the record already exists --
that limitation is deliberate and this is the other half of it.

## Safe to run repeatedly

Every repair goes through the same apply_once and grant_entitlement that the
webhook uses, and both are idempotent. Running this twice grants nothing twice.
Running it while a webhook is arriving for the same session grants once.

## Read-only unless asked

Defaults to reporting. A job that silently grants entitlements the first time
somebody runs it by hand is a job nobody trusts enough to run.
"""

from __future__ import annotations

import argparse
import sys

import stripe_billing

# How far back to look. Stripe retries for three days, so anything older than
# that is not a delivery still in flight -- it is a delivery that failed.
DEFAULT_LOOKBACK_DAYS = 7

# Stripe's own status for a session whose money actually arrived. A session can
# be `complete` with `payment_status` unpaid on some flows, which is exactly the
# distinction that would otherwise grant the product for free.
PAID_STATUS = "paid"


def missing_fulfilments(stripe_sessions, event_store, entitlement_reader):
    """Sessions Stripe considers paid that we never granted.

    Pure: it takes the two lists and returns the difference, so the decision is
    testable without a network or a database.
    """
    problems = []
    for session in stripe_sessions:
        if session.get("payment_status") != PAID_STATUS:
            continue

        user_id = session.get("client_reference_id") or (session.get("metadata") or {}).get(
            "user_id"
        )
        if not user_id:
            problems.append(
                {
                    "session_id": session.get("id"),
                    "user_id": None,
                    "reason": "paid but carries no user id",
                    "repairable": False,
                }
            )
            continue

        if entitlement_reader(user_id):
            continue

        problems.append(
            {
                "session_id": session.get("id"),
                "user_id": user_id,
                "reason": "paid but not entitled",
                "repairable": True,
            }
        )
    return problems


def stalled_events(event_store, provider=stripe_billing.PROVIDER, limit=100):
    """Events we recorded and never finished with.

    A provider redelivery will not retry these -- the record already exists, so
    apply_once sees a duplicate. This is the only thing that will.
    """
    return [
        {
            "event_id": event.event_id,
            "type": event.type,
            "error": event.error,
            "user_id": stripe_billing.user_id_from_event({"data": {"object": event.payload}}),
        }
        for event in event_store.unprocessed(provider, limit)
    ]


def repair(problems, entitlements, dry_run=True):
    """Grant what is owed. Idempotent, because grant_entitlement is.

    Returns what it did, so a scheduled run can say nothing when there is
    nothing to say and shout when there is.
    """
    repaired = []
    for problem in problems:
        if not problem.get("repairable") or not problem.get("user_id"):
            continue
        if not dry_run:
            entitlements.grant(
                problem["user_id"],
                source=stripe_billing.PROVIDER,
                reference=problem.get("session_id") or problem.get("event_id"),
            )
        repaired.append(problem)
    return repaired


def fetch_recent_sessions(config, days=DEFAULT_LOOKBACK_DAYS, client=None):
    """Recent Checkout sessions, as plain dicts.

    Returns dicts rather than Stripe objects so everything above this line can
    be tested with fixtures.
    """
    import time

    stripe = client or _stripe(config)
    created_after = int(time.time()) - days * 86400

    sessions = []
    for session in stripe.checkout.Session.list(
        created={"gte": created_after}, limit=100
    ).auto_paging_iter():
        sessions.append(
            {
                "id": session.get("id"),
                "payment_status": session.get("payment_status"),
                "client_reference_id": session.get("client_reference_id"),
                "metadata": dict(session.get("metadata") or {}),
            }
        )
    return sessions


def _stripe(config):
    import stripe

    stripe.api_key = config.stripe_secret_key
    return stripe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument(
        "--repair",
        action="store_true",
        help="actually grant what is owed. Without this, reports and changes nothing.",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    from config import load_config
    from entitlements import PostgresEntitlements
    from payment_events import PostgresPaymentEventStore

    from supabase import create_client

    config = load_config()
    if not stripe_billing.is_configured(config):
        print("payments are not configured; nothing to reconcile")
        return 0
    config.require_database()

    client = create_client(config.supabase_url, config.supabase_service_key)
    entitlements = PostgresEntitlements(client)
    event_store = PostgresPaymentEventStore(client)

    sessions = fetch_recent_sessions(config, args.days)
    problems = missing_fulfilments(sessions, event_store, entitlements.is_unlimited)
    stalled = stalled_events(event_store)

    print(f"checked {len(sessions)} Stripe sessions from the last {args.days} days")
    print(f"  paid but not entitled: {len(problems)}")
    print(f"  events received and never applied: {len(stalled)}")

    for problem in problems:
        print(f"    {problem['session_id']}: {problem['reason']} (user {problem['user_id']})")
    for event in stalled:
        print(f"    {event['event_id']} ({event['type']}): {event['error']}")

    if not problems and not stalled:
        print("nothing to repair")
        return 0

    if not args.repair:
        print("\nrun again with --repair to grant what is owed")
        # Non-zero so a scheduled run fails loudly rather than passing quietly
        # with somebody's purchase still unfulfilled.
        return 1

    repaired = repair(problems, entitlements, dry_run=False)
    for event in stalled:
        if event["user_id"]:
            entitlements.grant(
                event["user_id"], source=stripe_billing.PROVIDER, reference=event["event_id"]
            )
            event_store.complete(stripe_billing.PROVIDER, event["event_id"])
            repaired.append(event)

    print(f"\nrepaired {len(repaired)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
