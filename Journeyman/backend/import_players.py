"""Seed the players table from backend/nba_players.json.

Run once to move the existing pool into Postgres:

    python backend/import_players.py --activate-ok

Nothing is promoted into the puzzle rotation unless --activate-ok is passed, and
even then only careers validation cleared. Anything flagged stays inactive for a
person to look at:

    python backend/import_players.py --review
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import load_config  # noqa: E402
from difficulty import describe, difficulty_for, is_daily_eligible, should_promote  # noqa: E402
from players_repo import PlayersRepo  # noqa: E402
from validation import format_report, validate_pool  # noqa: E402

SOURCE = "nba_players.json"
POOL_PATH = Path(__file__).with_name("nba_players.json")


def _repo():
    from supabase import create_client

    config = load_config()
    config.require_database()
    return PlayersRepo(create_client(config.supabase_url, config.supabase_service_key))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--promote",
        action="store_true",
        help="promote careers that meet the promotion rule into the puzzle rotation",
    )
    parser.add_argument("--review", action="store_true", help="print the review queue and exit")
    parser.add_argument("--dry-run", action="store_true", help="validate but write nothing")
    args = parser.parse_args(argv)

    if args.review:
        for player in _repo().needing_review():
            print(f"[{player['validation_status']}] {player['name']}: {player['validation_notes']}")
        return 0

    with POOL_PATH.open(encoding="utf-8") as f:
        players = json.load(f)["players"]

    print(format_report(validate_pool(players)))
    print()

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    repo = _repo()
    written = repo.upsert_many(players, source=SOURCE)
    print(f"wrote {written} players")

    if args.promote:
        # A rule rather than a person: hand-review works at 200 players and not
        # at several thousand. What stays hand-reviewed is the schedule.
        promoted = [
            p
            for p in players
            if should_promote(
                p.get("ppg"),
                len(set(p["teams"])),
                "ok" if validate_pool([p])["ok"] else "review",
            )
        ]
        for player in promoted:
            repo.set_active(player["id"], True)

        tiers = {}
        for player in promoted:
            tier = difficulty_for(player.get("ppg"), len(player["teams"]))
            tiers[tier] = tiers.get(tier, 0) + 1

        print(f"promoted {len(promoted)}; the rest await review")
        for tier in sorted(tiers):
            marker = "daily" if is_daily_eligible(tier) else "     "
            print(f"  tier {tier} [{marker}] {tiers[tier]:4}  {describe(tier)}")

    print(f"pool: {repo.counts()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
