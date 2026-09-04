"""Seed the daily puzzle calendar.

    python backend/schedule_puzzles.py --days 90

Fills every unscheduled date in the window from the promoted pool, skipping
players used in the last six months. Existing rows are never overwritten -- a
scheduled puzzle is a promise.

    python backend/schedule_puzzles.py --show
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import load_config  # noqa: E402
from difficulty import describe, is_daily_eligible  # noqa: E402
from generate_players import today_eastern  # noqa: E402
from players_repo import PlayersRepo, teams_of  # noqa: E402
from puzzles_repo import NotEnoughPlayers, PuzzlesRepo, plan  # noqa: E402


def _client():
    from supabase import create_client

    config = load_config()
    config.require_database()
    return create_client(config.supabase_url, config.supabase_service_key)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90, help="how far ahead to fill")
    parser.add_argument("--show", action="store_true", help="print the calendar and exit")
    parser.add_argument("--dry-run", action="store_true", help="plan but write nothing")
    args = parser.parse_args(argv)

    client = _client()
    puzzles = PuzzlesRepo(client)
    start = today_eastern()
    end = start + timedelta(days=args.days - 1)

    if args.show:
        for date, row in sorted(puzzles.scheduled_between(start, end).items()):
            print(f"{date}  {(row.get('payload') or {}).get('player_name', '?')}")
        return 0

    pool = [
        {
            "id": row["id"],
            "name": row["name"],
            "teams": teams_of(row),
            "difficulty": row.get("difficulty"),
        }
        for row in PlayersRepo(client).active_pool()
    ]

    eligible = sum(1 for p in pool if is_daily_eligible(p["difficulty"]))
    print(f"{len(pool)} promoted players, {eligible} of them daily-eligible")
    if eligible < args.days:
        # Said plainly rather than buried: the calendar will reach past the
        # recognisable players and start using harder ones.
        print(
            f"  note: fewer daily-eligible players ({eligible}) than days to fill "
            f"({args.days}), so harder careers will be used once they run out"
        )

    try:
        chosen = plan(
            pool,
            start,
            args.days,
            already_scheduled=puzzles.scheduled_between(start, end),
            last_used=puzzles.last_used(start),
            prefer=lambda p: is_daily_eligible(p["difficulty"]),
        )
    except NotEnoughPlayers as exc:
        print(f"cannot schedule: {exc}")
        return 1

    print(f"{len(chosen)} dates to fill")
    for date, player in chosen[:5]:
        tier = player.get("difficulty")
        print(f"  {date}  {player['name']:24} tier {tier or '?'} ({describe(tier)})")
    if len(chosen) > 5:
        print(f"  ... and {len(chosen) - 5} more")

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    for date, player in chosen:
        puzzles.schedule(date, player)
    print(f"\nscheduled {len(chosen)} puzzles through {end}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
