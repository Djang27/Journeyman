"""Build the player pool from the Basketball-Reference season data.

Run when the pool needs refreshing, not on a schedule and never during a
request. Downloads the CC0 Kaggle dataset, derives careers, and writes
nba_players.json -- which stays in the repo as the degraded-mode fallback and as
the input to import_players.py.

    python backend/build_pool.py                 # download and rebuild
    python backend/build_pool.py --from /tmp/csv # reuse files already downloaded
    python backend/build_pool.py --dry-run       # report without writing

Needs the Kaggle CLI authenticated (~/.kaggle/access_token) for the download
only. Nothing at runtime touches Kaggle.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from br_source import build_pool  # noqa: E402
from difficulty import describe, difficulty_for, is_daily_eligible, should_promote  # noqa: E402
from validation import validate  # noqa: E402

DATASET = "sumitrodatta/nba-aba-baa-stats"
FILES = {
    "seasons": "Player Season Info.csv",
    "totals": "Player Totals.csv",
    "all_star": "All-Star Selections.csv",
}
OUTPUT = Path(__file__).with_name("nba_players.json")

# A career needs somewhere to go for the game to be a game.
MIN_DISTINCT_FRANCHISES = 2


def download(target):
    """Fetch the three CSVs. The Kaggle CLI writes URL-encoded filenames."""
    for label, name in FILES.items():
        subprocess.run(
            ["kaggle", "datasets", "download", DATASET, "-f", name, "--unzip", "-q", "-p", target],
            check=True,
        )
        encoded = Path(target) / name.replace(" ", "%20")
        if encoded.exists():
            encoded.rename(Path(target) / f"{label}.csv")
        else:
            (Path(target) / name).rename(Path(target) / f"{label}.csv")
    return {label: str(Path(target) / f"{label}.csv") for label in FILES}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="source_dir", help="directory holding the CSVs already")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args(argv)

    with tempfile.TemporaryDirectory() as tmp:
        if args.source_dir:
            paths = {label: f"{args.source_dir}/{label}.csv" for label in FILES}
        else:
            print(f"downloading {DATASET} ...")
            paths = download(tmp)

        careers, skipped = build_pool(paths["seasons"], paths["totals"], paths["all_star"])

    print(f"careers built: {len(careers)}, skipped for an unnameable franchise: {skipped}")

    players = []
    ambiguous = 0
    for career in careers:
        if len(set(career["teams"])) < MIN_DISTINCT_FRANCHISES:
            continue
        if career["ambiguous_seasons"]:
            # Kept in the file so a reviewer can see them, but validation and the
            # curation gate keep them out of the rotation.
            ambiguous += 1

        career["difficulty"] = difficulty_for(
            career["ppg"],
            len(career["teams"]),
            career["games"],
            career["all_star_selections"],
        )
        players.append(career)

    players.sort(key=lambda p: p["name"])

    promotable = [
        p
        for p in players
        if not p["ambiguous_seasons"]
        and should_promote(
            p["ppg"], len(set(p["teams"])), validate(p["teams"])["verdict"], p["games"]
        )
    ]
    daily = [p for p in promotable if is_daily_eligible(p["difficulty"])]

    print(f"\nmulti-franchise careers: {len(players)}")
    print(f"  with an unresolvable trade order: {ambiguous}  (held for review)")
    print(f"  promotable: {len(promotable)}")
    print(f"  daily-eligible: {len(daily)}")

    tiers = {}
    for player in promotable:
        tiers[player["difficulty"]] = tiers.get(player["difficulty"], 0) + 1
    for tier in sorted(tiers):
        marker = "daily" if is_daily_eligible(tier) else "     "
        print(f"    tier {tier} [{marker}] {tiers[tier]:5}  {describe(tier)}")

    if args.dry_run:
        print("\ndry run: nothing written")
        return 0

    OUTPUT.write_text(
        json.dumps(
            {
                "generated_at": date.today().isoformat(),
                "source": DATASET,
                "source_licence": "CC0-1.0",
                "players": players,
            },
            indent=1,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\nwrote {len(players)} careers to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
