"""Seed the daily puzzle calendar.

    python backend/schedule_puzzles.py --days 90

Fills every unscheduled date in the window from the promoted pool, skipping
players used in the last six months. Existing rows are never overwritten -- a
scheduled puzzle is a promise.

    python backend/schedule_puzzles.py --show
"""

import argparse
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import load_config  # noqa: E402
from difficulty import (  # noqa: E402
    DAILY_MAX_FAME,
    daily_fit,
    daily_target,
    describe,
    fame_for,
    week_shape,
)
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
    parser.add_argument(
        "--redo-future",
        action="store_true",
        help=(
            "delete every puzzle scheduled after today and fill the window again. "
            "For applying changed scheduling rules to a calendar already filled. "
            "Today and the archive are never touched."
        ),
    )
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
            # The fame floor is the rule that keeps a daily fair, so the
            # scheduler has to see it and not only the composite rating.
            "last_season": row.get("last_season"),
            "fame": fame_for(
                row.get("career_ppg"),
                row.get("career_games"),
                row.get("all_star_selections") or 0,
            ),
        }
        for row in PlayersRepo(client).active_pool()
    ]

    fair = [p for p in pool if p["fame"] is not None and p["fame"] <= DAILY_MAX_FAME]
    print(f"{len(pool)} promoted players, {len(fair)} of them fit to be a daily")
    print("  week: " + "  ".join(f"{name} {target}" for name, target in week_shape()))
    if len(fair) < args.days:
        # Said plainly rather than buried: the calendar will reach past the
        # recognisable players and start using harder ones.
        print(
            f"  note: fewer fit players ({len(fair)}) than days to fill "
            f"({args.days}), so less recognisable careers will be used once they run out"
        )

    if args.redo_future:
        # Strictly after today. Today's may be halfway through being played,
        # and the past is the archive people have paid for.
        if args.dry_run:
            later = {
                d: r for d, r in puzzles.scheduled_between(start, end).items() if d > str(start)
            }
            print(f"\ndry run: would delete {len(later)} scheduled puzzles after {start}")
        else:
            removed = puzzles.unschedule_between(start, end)
            print(f"\ncleared {removed} scheduled puzzles after {start}")

    already = puzzles.scheduled_between(start, end)
    if args.redo_future and args.dry_run:
        already = {d: r for d, r in already.items() if d <= str(start)}

    try:
        chosen = plan(
            pool,
            start,
            args.days,
            already_scheduled=already,
            last_used=puzzles.last_used(start),
            fit=daily_fit,
            # Seeded from the window, so --dry-run and the run that follows it
            # choose the same players. Unseeded, the preview showed a different
            # calendar from the one that got written -- which made "read the dry
            # run before trusting it" a check on the shape and nothing more.
            rng=random.Random(f"{start}:{args.days}"),
        )
    except NotEnoughPlayers as exc:
        print(f"cannot schedule: {exc}")
        return 1

    print(f"\n{len(chosen)} dates to fill")
    for date, player in chosen[:7]:
        tier = player.get("difficulty")
        aimed = daily_target(date)
        mark = "" if tier == aimed else f"  (aimed {aimed})"
        print(
            f"  {date} {date.strftime('%a')}  {player['name']:24} "
            f"tier {tier or '?'} ({describe(tier)}){mark}"
        )
    if len(chosen) > 7:
        print(f"  ... and {len(chosen) - 7} more")

    off = sum(1 for date, player in chosen if player.get("difficulty") != daily_target(date))
    if off:
        print(f"  {off} of {len(chosen)} could not be matched exactly; nearest tier used")

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    for date, player in chosen:
        puzzles.schedule(date, player)
    print(f"\nscheduled {len(chosen)} puzzles through {end}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
