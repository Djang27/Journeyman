"""Scoring a candidate player-data source against hand-verified careers.

Phase 1 has to choose where puzzle content comes from, and the honest way to
choose is to check candidates against careers a person has confirmed rather than
against each other. See docs/nba-data.md.

Entries that have not been verified are ignored throughout, so the fixture is
useful from the first one filled in rather than only when it is complete.
"""

from __future__ import annotations

import json
from pathlib import Path

GROUND_TRUTH_PATH = Path(__file__).parent / "tests" / "fixtures" / "ground_truth.json"


def load_ground_truth(path=None):
    """Every entry, verified or not."""
    with open(path or GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)["players"]


def verified_entries(path=None):
    """Only entries a person has confirmed. The ones worth scoring against."""
    return [p for p in load_ground_truth(path) if p.get("verified") and p.get("verified_teams")]


def compare(expected, actual):
    """Grade one career against its verified truth.

    Returns a dict describing *how* it differs, not just whether -- the failure
    mode is what distinguishes a source that is unusable from one that needs a
    small fix. A source that drops relocations is broken; one that merely
    disagrees about a ten-day contract is fine.
    """
    expected = list(expected or [])
    actual = list(actual or [])

    if expected == actual:
        return {"match": "exact", "detail": None}

    if [t for t in actual if t] == [t for t in expected if t]:
        return {"match": "exact", "detail": None}

    # Multiset first, then set. The order matters: a dropped return has the same
    # *set* of franchises as the truth but one fewer stint, and reporting that as
    # a reordering would point at the wrong bug entirely.
    if sorted(expected) == sorted(actual):
        # Every stint present, sequenced wrongly -- the signature of a mid-season
        # trade whose rows were interleaved rather than ordered.
        return {"match": "order", "detail": {"expected": expected, "actual": actual}}

    if set(expected) == set(actual):
        # Right franchises, wrong number of stints: a return was collapsed away,
        # or one was invented.
        return {"match": "stints", "detail": {"expected": expected, "actual": actual}}

    return {
        "match": "wrong",
        "detail": {
            "missing": [t for t in expected if t not in actual],
            "extra": [t for t in actual if t not in expected],
        },
    }


def score_source(lookup, path=None):
    """Run a candidate source over every verified career.

    `lookup` takes a player_id and returns that source's team sequence, or None
    when it has no answer -- which is itself a finding worth counting.
    """
    results = []
    for entry in verified_entries(path):
        try:
            actual = lookup(entry["player_id"])
        except Exception as exc:  # a source that errors is a source that failed
            results.append({"name": entry["name"], "match": "error", "detail": str(exc)})
            continue

        if actual is None:
            results.append({"name": entry["name"], "match": "absent", "detail": None})
            continue

        outcome = compare(entry["verified_teams"], actual)
        results.append({"name": entry["name"], **outcome})

    return {
        "total": len(results),
        "exact": sum(1 for r in results if r["match"] == "exact"),
        "by_failure": _counts(r["match"] for r in results if r["match"] != "exact"),
        "results": results,
    }


def _counts(values):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def format_report(score):
    """A short report, so a comparison can be pasted into docs/nba-data.md."""
    if score["total"] == 0:
        return "No verified ground truth yet -- nothing to score against."

    lines = [f"{score['exact']}/{score['total']} careers exactly correct"]
    for failure, count in sorted(score["by_failure"].items()):
        lines.append(f"  {count} x {failure}")
    for result in score["results"]:
        if result["match"] != "exact":
            lines.append(f"  - {result['name']}: {result['match']}")
    return "\n".join(lines)
