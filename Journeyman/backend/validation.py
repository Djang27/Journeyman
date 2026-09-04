"""Checking player careers without a source to check them against.

Hand-verification does not scale: a few thousand careers cannot be read by a
person, and a source that is 95% right still means a hundred broken puzzles.
What scales is layering checks so that only the doubtful cases need a human.

Three layers, in order of confidence:

* **Impossible** -- a franchise appearing before its own earlier name. Provably
  wrong with no external source, and no false positives, so these can be
  rejected automatically.
* **Implausible** -- patterns that are rare in reality rather than impossible,
  such as a career alternating A/B/A/B. These produce a review queue. They are
  the layer that found the pre-1985 ordering bug in the original pool: three
  careers out of two hundred, all with the same fingerprint, all wrong.
* **Unverified** -- everything that passes. Combined with the curation gate on
  `players.is_active_for_puzzles`, no career reaches a player until someone
  promotes it.

Cross-source agreement is the fourth layer and lives in the ingestion job: two
independent sources that agree are accepted, and disagreements join the review
queue. See docs/nba-data.md.
"""

from __future__ import annotations

# Franchises that changed name or city. The earlier name can never appear after
# the later one in the same career, because it is the same club.
SUCCESSION = (
    ("seattle supersonics", "oklahoma city thunder"),
    ("vancouver grizzlies", "memphis grizzlies"),
    ("new jersey nets", "brooklyn nets"),
    ("washington bullets", "washington wizards"),
    # Charlotte is the awkward one: the original Hornets left for New Orleans in
    # 2002, the Bobcats arrived in 2004 and took the Hornets name in 2014. A
    # career can hold both, but Bobcats can never follow that second Hornets era.
    ("charlotte bobcats", "charlotte hornets"),
    ("new orleans hornets", "new orleans pelicans"),
)

# Above this, a career is unusual enough to be worth a glance. Real journeymen do
# reach thirteen stints, so this flags rather than rejects.
MANY_STINTS = 10

# A franchise revisited this many times is rare enough to be suspicious.
MANY_REVISITS = 3


def impossible_problems(teams):
    """Errors provable without any source. Safe to reject on."""
    problems = []

    for earlier, later in SUCCESSION:
        if earlier in teams and later in teams and teams.index(later) < teams.index(earlier):
            problems.append(
                f"{later!r} appears before {earlier!r}, but they are the same franchise"
            )

    # strict=False on purpose: the two slices differ in length by one.
    for index, (first, second) in enumerate(zip(teams, teams[1:], strict=False)):
        if first == second:
            problems.append(f"consecutive duplicate stint at position {index}: {first!r}")

    if not teams:
        problems.append("no teams at all")

    return problems


def implausible_problems(teams):
    """Patterns that are rare rather than impossible. These queue for review."""
    problems = []

    alternations = sum(
        1
        for i in range(len(teams) - 3)
        if teams[i] == teams[i + 2] and teams[i + 1] == teams[i + 3]
    )
    if alternations:
        # Two franchises trading a player back and forth is vanishingly rare.
        # Interleaved rows from a mid-season trade look exactly like this, which
        # is what it caught in the original pool.
        problems.append(
            f"{alternations} A/B/A/B alternation(s): likely interleaved mid-season rows"
        )

    if len(teams) > MANY_STINTS:
        problems.append(f"{len(teams)} stints, above the {MANY_STINTS} worth checking")

    revisits = len(teams) - len(set(teams))
    if revisits >= MANY_REVISITS:
        problems.append(f"{revisits} revisits to a former franchise")

    if len(set(teams)) < 2:
        # Not wrong as data, but unusable: the game is about a career path.
        problems.append("fewer than two distinct franchises")

    return problems


def validate(teams):
    """Grade one career. `verdict` is reject, review, or ok."""
    impossible = impossible_problems(teams)
    implausible = implausible_problems(teams)

    if impossible:
        verdict = "reject"
    elif implausible:
        verdict = "review"
    else:
        verdict = "ok"

    return {"verdict": verdict, "impossible": impossible, "implausible": implausible}


def validate_pool(players):
    """Run over a whole pool. `players` is dicts with `name` and `teams`."""
    graded = []
    for player in players:
        result = validate(player.get("teams") or [])
        graded.append({"name": player.get("name", "?"), **result})

    return {
        "total": len(graded),
        "ok": sum(1 for g in graded if g["verdict"] == "ok"),
        "review": [g for g in graded if g["verdict"] == "review"],
        "reject": [g for g in graded if g["verdict"] == "reject"],
    }


def format_report(summary):
    total = summary["total"]
    review, reject = summary["review"], summary["reject"]

    lines = [
        f"{total} careers: {summary['ok']} ok, {len(review)} to review, {len(reject)} rejected",
    ]
    if total:
        lines.append(f"review rate: {len(review) / total:.1%}")

    for group, label in ((reject, "REJECT"), (review, "REVIEW")):
        for entry in group:
            reasons = "; ".join(entry["impossible"] + entry["implausible"])
            lines.append(f"  [{label}] {entry['name']}: {reasons}")

    return "\n".join(lines)
