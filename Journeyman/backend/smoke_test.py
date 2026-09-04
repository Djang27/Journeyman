"""Play a real game against a deployment and check it behaved.

The two worst bugs in this project raised no exception. The leaderboard returned
an empty list for months, and every daily 500'd only after a foreign key it had
never been given. An error tracker sees neither: nothing threw, or nothing was
running when it did.

What catches "works, but wrong" is asserting the things that must be true, from
outside, on a schedule, against the real thing. That is what this does.

    python backend/smoke_test.py --url https://journeyman.example
    python backend/smoke_test.py --url ... --mode daily

Exits non-zero when any check fails, so a scheduled job turns red rather than
quietly succeeding.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request


class CheckFailed(Exception):
    pass


class Client:
    def __init__(self, base_url, timeout=20):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.status, json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode()
            try:
                return exc.code, json.loads(payload or "{}")
            except json.JSONDecodeError:
                # An HTML error page from a proxy means the request never
                # reached the app -- worth distinguishing from a real 4xx.
                raise CheckFailed(
                    f"{method} {path} returned {exc.code} with a non-JSON body"
                ) from exc


def check(condition, message):
    if not condition:
        raise CheckFailed(message)
    print(f"  ok  {message}")


def run(client, mode="unlimited"):
    """Play one game through and assert what must be true of it."""
    print(f"health check at {client.base}")
    status, health = client.request("GET", "/api/health")
    check(status == 200, f"health returns 200 (got {status})")
    check(health.get("status") == "ok", f"health is ok (got {health.get('status')})")
    check(
        health.get("persistent") is True,
        "sessions are persistent -- an in-memory store loses them between requests",
    )
    check(health.get("database_reachable") is not False, "the database is reachable")

    print(f"\nstarting a {mode} game")
    status, game = client.request("POST", "/api/game/start", {"mode": mode})
    if status == 409:
        print("  --  today's daily is already played by this caller; nothing to check")
        return
    check(status == 201, f"start returns 201 (got {status}: {game.get('error')})")

    session_id = game.get("session_id")
    check(bool(session_id), "a session id came back")
    check(game.get("num_teams", 0) >= 2, "the puzzle has at least two stops")

    # The property Phase 0 exists for. Checked against the raw payload rather
    # than a parsed field, so a leak through any key is caught.
    check("teams" not in game, "the answer is NOT in the start response")
    check("answer" not in json.dumps(game).lower(), "no 'answer' key on the wire")

    print("\nplaying it out")
    status, guessed = client.request(
        "POST", f"/api/game/{session_id}/guess", {"position": 0, "guess": "not a real team"}
    )
    check(status == 200, f"a guess is graded (got {status})")
    check(guessed["results"][0] in ("green", "yellow", "gray"), "the guess got a colour")
    check("teams" not in guessed, "the answer is still hidden mid-game")

    print("\nrejecting nonsense")
    status, _ = client.request(
        "POST", f"/api/game/{session_id}/guess", {"position": -1, "guess": "x"}
    )
    check(status == 400, f"a negative position is refused (got {status})")

    status, _ = client.request(
        "POST",
        "/api/game/00000000-0000-0000-0000-000000000000/guess",
        {"position": 0, "guess": "x"},
    )
    check(status == 404, f"an unknown session is a 404 (got {status})")

    print("\nabandoning")
    status, done = client.request("POST", f"/api/game/{session_id}/abandon")
    check(status == 200, f"the game can be abandoned (got {status})")
    check(done.get("status") == "abandoned", "it is recorded as abandoned")
    # Only once the game is over should the career appear.
    check("teams" in done, "the answer IS revealed once the game is over")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="base URL of the deployment")
    parser.add_argument("--mode", default="unlimited", choices=["unlimited", "daily"])
    args = parser.parse_args(argv)

    try:
        run(Client(args.url), args.mode)
    except CheckFailed as exc:
        print(f"\nFAILED: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 -- a smoke test reports, it does not raise
        print(f"\nFAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
