import logging

import archive
import stripe_billing
from admin import AdminError, AdminOperations, is_authorised, token_from_headers
from auth import AuthError, user_id_from_headers
from config import load_config
from daily_cache import DEFAULT_TTL_SECONDS, PuzzleCache
from entitlements import FreeTierOnly
from flask import Flask, jsonify, request
from generate_players import daily_player, randomPlayer, today_eastern, use_pool_source
from observability import (
    SENTRY_ACTIVE,
    RequestTimer,
    configure_logging,
    configure_sentry,
    get_request_id,
    new_request_id,
    safe_headers,
    set_request_id,
)
from payment_events import InMemoryPaymentEventStore, apply_once
from quota import (
    FREE_GAMES_PER_DAY,
    InMemoryQuotaStore,
)
from quota import (
    consume as consume_quota,
)
from rate_limit import (
    CHECKOUT_LIMIT,
    GUESS_LIMIT,
    START_LIMIT,
    InMemoryRateLimiter,
    check,
)
from sessions import (
    GAME_SLUG,
    InMemorySessionStore,
    SessionError,
    SessionNotFound,
    abandon,
    public_view,
    resume_daily,
    set_hard_mode,
    start_session,
    submit_guess,
    use_hint,
)
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

_boot_config = load_config()
configure_logging()
SENTRY_STATUS = configure_sentry(
    _boot_config.sentry_dsn,
    environment=_boot_config.environment,
    release=_boot_config.release,
)
SENTRY_ENABLED = SENTRY_STATUS == SENTRY_ACTIVE
logger = logging.getLogger("journeyman")


# Paths that keep working during maintenance: health, so a monitor can see the
# state rather than a generic failure, and admin, so the person fixing it is not
# locked out by their own switch.
#
# The billing webhook is exempt too, and for a different reason from the other
# two: a rejected webhook is a payment event lost. Stripe retries for three
# days, so a short window is survivable, but there is no reason to spend that
# budget on our own maintenance switch -- and the events arrive during exactly
# the incident nobody is watching.
MAINTENANCE_EXEMPT = ("/api/health", "/api/admin/", "/api/billing/webhook")


@app.before_request
def _reject_during_maintenance():
    """Fail honestly during planned downtime.

    Not a way to keep playing: since Phase 0 every game start writes a session
    row, so there is no read-only mode in which the game still works. This turns
    an outage into a message a person can read.
    """
    if not config.maintenance_mode:
        return None
    if request.path.startswith(MAINTENANCE_EXEMPT):
        return None

    response = jsonify({"error": config.maintenance_message, "maintenance": True})
    # 503 with Retry-After, so monitors and crawlers treat it as temporary
    # rather than as the game having ceased to exist.
    response.headers["Retry-After"] = "300"
    return response, 503


@app.before_request
def _start_request():
    """Tag the request so every line it produces can be found together."""
    request_id = set_request_id(new_request_id(request.headers))
    request.environ["journeyman.timer"] = RequestTimer(
        logger, request.method, request.path, request_id
    )


@app.after_request
def _finish_request(response):
    timer = request.environ.get("journeyman.timer")
    if timer:
        timer.finish(response.status_code)
    # Echoed so a player reporting a problem can quote an id that finds the
    # exact request in the log.
    response.headers["X-Request-Id"] = get_request_id()
    return response


def _build_session_store():
    """Postgres when configured, in-memory otherwise.

    The in-memory fallback keeps `python app.py` and the test suite working with
    no setup. It is NOT viable in production: each serverless invocation gets its
    own empty dict, so /guess would not find what /start created. Deployments
    must set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.
    """
    config = load_config()
    if not config.use_database:
        return InMemorySessionStore()

    from supabase_store import SupabaseSessionStore

    return SupabaseSessionStore.from_config(config)


def _wire_player_pool(config):
    """Point player selection at the players table when there is one.

    Without this the game reads nba_players.json, which has no curation gate --
    a career flagged for review would still be served as a puzzle.
    """
    if not config.use_database:
        return None

    from players_repo import PlayersRepo, teams_of

    from supabase import create_client

    repo = PlayersRepo(create_client(config.supabase_url, config.supabase_service_key))

    def fetch():
        return [
            {"id": row["id"], "name": row["name"], "teams": teams_of(row)}
            for row in repo.active_pool()
        ]

    use_pool_source(fetch)
    return repo


session_store = _build_session_store()
config = load_config()
players_repo = _wire_player_pool(config)


def _build_puzzles_repo(config):
    if not config.use_database:
        return None

    from puzzles_repo import PuzzlesRepo

    from supabase import create_client

    return PuzzlesRepo(create_client(config.supabase_url, config.supabase_service_key))


puzzles_repo = _build_puzzles_repo(config)

# Today's puzzle is one row that every daily start reads and that changes at
# most once a day. See daily_cache for why this is in-process with a short TTL
# rather than at the edge until midnight, which is what the roadmap called for.
daily_cache = PuzzleCache()


def _build_rate_limiter(config):
    """Postgres when configured, in-memory otherwise.

    The in-memory one is for tests and single-process local runs. On serverless
    each invocation has its own dict, so the effective limit would multiply by
    however many instances are warm.
    """
    if not config.use_database:
        return InMemoryRateLimiter()

    from rate_limit import PostgresRateLimiter

    from supabase import create_client

    return PostgresRateLimiter(create_client(config.supabase_url, config.supabase_service_key))


rate_limiter = _build_rate_limiter(config)


def _build_quota_store(config):
    """Postgres when configured, in-memory otherwise.

    The in-memory one is for tests and local runs. On serverless each invocation
    has its own dict, so an allowance would reset whenever a new instance served
    the request -- which is to say, it would not be an allowance.
    """
    if not config.use_database:
        return InMemoryQuotaStore()

    from quota import PostgresQuotaStore

    from supabase import create_client

    return PostgresQuotaStore(create_client(config.supabase_url, config.supabase_service_key))


quota_store = _build_quota_store(config)


def _build_entitlements(config):
    """Reads the entitlements table when there is one, else nobody is entitled.

    FreeTierOnly is also the right answer for a database-less local run: no
    table, so nobody has bought anything.
    """
    if not config.use_database:
        return FreeTierOnly()

    from entitlements import PostgresEntitlements

    from supabase import create_client

    return PostgresEntitlements(create_client(config.supabase_url, config.supabase_service_key))


entitlements = _build_entitlements(config)

# A syntactically valid uuid that belongs to nobody, so the health probe
# exercises the real query without naming a real person.
_HEALTH_PROBE_USER = "00000000-0000-0000-0000-000000000000"


def _build_payment_events(config):
    if not config.use_database:
        return InMemoryPaymentEventStore()

    from payment_events import PostgresPaymentEventStore

    from supabase import create_client

    return PostgresPaymentEventStore(
        create_client(config.supabase_url, config.supabase_service_key)
    )


payment_events = _build_payment_events(config)


def _quota_exhausted(mode, user_id):
    """Spends one game and returns a 402 when the allowance is gone, else None.

    Also returns the decision, so the caller can put what is left on a
    successful response without asking twice.

    Fails open, like the rate limiter, and for a reason worth stating rather
    than copying: if the quota store is unreachable the choice is between giving
    away some free games and stopping the game working. Free games are
    recoverable; an outage is not. It logs loudly, because silently free forever
    is a different problem from briefly free.
    """
    try:
        decision = consume_quota(
            quota_store,
            entitlements,
            mode,
            user_id,
            today_eastern().isoformat(),
            headers=request.headers,
        )
    except Exception:
        logger.exception("quota store unavailable", extra={"http_path": request.path})
        return None, None

    if decision.allowed:
        return None, decision

    # 402 rather than 429. A rate limit says "slow down" and resolves itself in
    # seconds; this says "you have used what is free", which is a different
    # thing for the UI to say and a different thing for a player to do about it.
    response = jsonify(
        {
            "error": "That is all five free games for today. The daily puzzle is always free.",
            "quota": {
                "used": decision.used,
                "remaining": 0,
                "limit": decision.limit,
                "resets": "midnight Eastern",
            },
        }
    )
    return (response, 402), decision


def _rate_limited(action, limit, user_id=None):
    """Returns a 429 response when the caller is over their limit, else None.

    Fails open: a limiter that is itself unavailable must not take the game
    down. It is not the security boundary -- identity and the curation gate are
    -- so trading a real outage for a hypothetical abuse is the wrong way round.
    """
    try:
        decision = check(rate_limiter, action, limit, user_id, request.headers)
    except Exception:
        logger.exception("rate limiter unavailable", extra={"http_path": request.path})
        return None

    if decision.allowed:
        return None

    response = jsonify({"error": "You are going a little fast. Try again in a moment."})
    retry_after = decision.retry_after_seconds
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)
    return response, 429


def _current_user_id():
    """The signed-in player, or None for anonymous play.

    Read from a verified token rather than the request body. A body field would
    let any caller write results under someone else's account, which is the last
    place the API still trusted the client.
    """
    return user_id_from_headers(
        request.headers,
        jwks_url=config.jwks_url,
        secret=config.supabase_jwt_secret,
    )


@app.route("/")
def home():
    return "Welcome to Journeyman"


@app.route("/api/health")
def api_health():
    """Liveness plus the one configuration fact worth checking from outside.

    `session_store` reports which store the process actually built, not what the
    environment claims. The in-memory fallback is silent by design -- it keeps
    local development working with no setup -- which makes it easy to deploy with
    a missing variable and not notice until sessions start vanishing between
    requests. This is how you notice.

    It also makes one cheap query, because knowing a store was *built* is not
    the same as knowing it works: this endpoint reported "persistent": true
    while Postgres was unreachable, and again while the tables were missing
    because a migration had never been applied.

    Deliberately says nothing about which project, which keys, or why a check
    failed: this endpoint is public, and "working or not" is the most it should
    ever reveal. The detail goes to the server log.
    """
    uses_database = type(session_store).__name__ != "InMemorySessionStore"

    database_ok = True
    if uses_database:
        try:
            session_store.check_reachable()
        except Exception:
            logger.exception("health check could not reach the database")
            database_ok = False

    # The quota fails open, which is right -- free games are recoverable and an
    # outage is not -- but it means a broken quota looks exactly like a working
    # game while every start is free. That happened: migration 0012 and the code
    # calling it shipped together, and production ran for minutes calling a
    # function that did not exist yet. Nothing caught it except an error report.
    # A read here is what lets the smoke test catch it next time.
    #
    # Both stores are probed, because a failure of either means unmetered play:
    # the quota refuses nobody if it cannot count, and an entitlement lookup
    # that raises is caught by the same fail-open path. Which one broke goes to
    # the log; this endpoint is public and says only whether metering works.
    quota_ok = True
    if uses_database:
        try:
            quota_store.used("health:probe", today_eastern().isoformat())
            entitlements.is_unlimited(_HEALTH_PROBE_USER)
        except Exception:
            logger.exception("health check could not reach the metering stores")
            quota_ok = False

    body = {
        "status": "maintenance"
        if config.maintenance_mode
        else ("ok" if database_ok else "degraded"),
        "session_store": "database" if uses_database else "memory",
        "persistent": uses_database,
        "database_reachable": database_ok if uses_database else None,
        # Whether errors are actually being captured, rather than leaving anyone
        # to assume they are.
        "error_reporting": SENTRY_ENABLED,
        # Why, not just whether. "false" alone sent an operator redeploying to
        # fix a variable that was never the problem: no_dsn means nothing
        # reached the process, sdk_missing means the dependency is absent, and
        # init_failed means the DSN itself was rejected.
        "error_reporting_status": SENTRY_STATUS,
        "maintenance": config.maintenance_mode,
        # Whether the daily puzzle is actually being served from memory. A hit
        # rate near zero on a busy deployment means instances are not being
        # reused, and every start is paying for a database read.
        "daily_cache": daily_cache.stats(),
        # Enforcing, or failing open and giving the game away. Not folded into
        # `status`: the game genuinely works with the quota down, so this must
        # not read as an outage to an uptime monitor.
        "quota_enforcing": quota_ok if uses_database else None,
    }

    # 503 so an uptime monitor treats this as down. Reporting 200 while the
    # database is unreachable is how an outage goes unnoticed.
    return jsonify(body), (200 if database_ok else 503)


# ---------------------------------------------------------------------------
# Session API
#
# The only way to play. The stateless /new-game, /daily-game and /check-guess
# endpoints are gone: they shipped the answer to the browser and graded a
# client-supplied answer against a client-supplied position, which is what made
# every score forgeable.
#
# No response below contains the answer while a game is in progress.
# ---------------------------------------------------------------------------


def _todays_puzzle(puzzle_date):
    """The scheduled puzzle for today, scheduling one only if none exists.

    Reading the row first is the point: once written, a day's puzzle is fixed.
    The hash fallback below is what the schedule replaced -- it stays so a gap in
    the calendar degrades to yesterday's behaviour instead of breaking the daily,
    but a scheduled row always wins.
    """
    cached = daily_cache.get(puzzle_date)
    if cached is not None:
        return cached

    if puzzles_repo is not None:
        row = puzzles_repo.get(puzzle_date)
        if row and row.get("payload"):
            payload = row["payload"]
            puzzle = (payload["player_name"], payload["teams"], payload["player_id"])
            daily_cache.put(puzzle_date, puzzle)
            return puzzle

    player_name, teams, player_id, _ = daily_player()

    # The session's composite foreign key requires the row to exist.
    session_store.ensure_puzzle(
        GAME_SLUG,
        puzzle_date,
        {"player_name": player_name, "player_id": player_id, "teams": teams},
    )

    # Cached too: the fallback is deterministic for the date, and the row has
    # just been written, so re-deriving it per request buys nothing.
    puzzle = (player_name, teams, player_id)
    daily_cache.put(puzzle_date, puzzle)
    return puzzle


def _with_quota(view, decision):
    """Attach what is left of the allowance to a session response.

    Omitted entirely when there is nothing to say -- an unmetered caller or a
    daily -- so the client can treat its absence as "not applicable" rather than
    having to interpret a zero.
    """
    if decision is None or decision.unmetered:
        return view
    return {**view, "quota": {"remaining": decision.remaining, "limit": decision.limit}}


def _session_error(exc, status):
    return jsonify({"error": str(exc)}), status


@app.errorhandler(Exception)
def _unhandled(exc):
    """Return JSON from the API rather than Flask's HTML error page.

    The client parses `error` out of the body; an HTML 500 gave players a bare
    "Something went wrong" with nothing in it to diagnose. The message stays
    generic on purpose -- the detail belongs in the server log, not in a
    response anyone can read.
    """
    if isinstance(exc, HTTPException):
        # 404, 405 and the like are already correct answers, not failures. They
        # are only reshaped into JSON for API callers; re-raising them here
        # turned every unknown path into a 500.
        if request.path.startswith("/api/"):
            return jsonify({"error": exc.description}), exc.code
        return exc

    if request.path.startswith("/api/"):
        logger.exception(
            "unhandled error",
            extra={"http_path": request.path, "headers": safe_headers(request.headers)},
        )
        return jsonify({"error": "The server hit an unexpected problem."}), 500

    logger.exception("unhandled error", extra={"http_path": request.path})
    raise exc


def _authorise(session):
    """Confirm the caller owns this session.

    A session belonging to an account may only be acted on by that account --
    otherwise a leaked or logged session id would let anyone else play out
    someone's daily and bank the score against their name.

    An anonymous session has no owner to check against, so possession of the id
    is the only credential there is. That is the cost of allowing play without
    an account, and it is bounded: the ids are random UUIDs, and an anonymous
    session writes no result anyone can claim.
    """
    if session.user_id is None:
        return None

    caller = _current_user_id()
    if caller != session.user_id:
        return jsonify({"error": "this game belongs to someone else"}), 403

    return None


@app.route("/api/game/start", methods=["POST"])
def api_game_start():
    body = request.get_json(silent=True) or {}
    mode = body.get("mode", "unlimited")
    hard_mode = bool(body.get("hard_mode", False))

    # Never body.get("user_id") -- see _current_user_id.
    try:
        user_id = _current_user_id()
    except AuthError as exc:
        return _session_error(exc, 401)

    limited = _rate_limited("game_start", START_LIMIT, user_id)
    if limited:
        return limited

    puzzle_date = None
    quota = None

    if mode == archive.MODE:
        if not user_id:
            return jsonify({"error": "Sign in to play the archive."}), 401
        if not entitlements.is_unlimited(user_id):
            # 402, matching the quota: this is a purchase away, not a mistake.
            return jsonify(
                {"error": "The archive is part of the unlimited unlock.", "locked": True}
            ), 402

        try:
            requested = archive.check_playable(body.get("puzzle_date"), today_eastern())
        except archive.ArchiveError as exc:
            return jsonify({"error": str(exc)}), 400

        puzzle_date = requested.isoformat()

        # Resumed rather than refused, exactly as the daily is.
        existing = session_store.find_dated(user_id, puzzle_date, archive.MODE)
        if existing is not None and not existing.is_finished:
            return jsonify(public_view(existing)), 200
        if existing is not None:
            return jsonify({"error": "You have already played that one."}), 409

        row = puzzles_repo.get(puzzle_date) if puzzles_repo else None
        payload = (row or {}).get("payload") or {}
        if not payload:
            return jsonify({"error": "No puzzle was scheduled for that date."}), 404

        player_name = payload["player_name"]
        teams = payload["teams"]
        player_id = payload["player_id"]

    elif mode == "daily":
        puzzle_date = today_eastern().isoformat()
        # Before building a new one: an unfinished daily is resumed, not
        # refused. The unique index would otherwise turn a page refresh into a
        # lockout for the rest of the day.
        existing = resume_daily(session_store, user_id, puzzle_date)
        if existing is not None:
            return jsonify(public_view(existing)), 200
        player_name, teams, player_id = _todays_puzzle(puzzle_date)
    else:
        # Charged before the game is built, so a refused start costs nothing
        # and cannot hand out a player the caller then keeps.
        refused, quota = _quota_exhausted(mode, user_id)
        if refused:
            return refused

        exclude = body.get("exclude") or []
        exclude_ids = {int(x) for x in exclude if str(x).strip().lstrip("-").isdigit()}
        player_name, teams, player_id = randomPlayer(exclude_ids=exclude_ids)

    try:
        session = start_session(
            session_store,
            mode=mode,
            player_name=player_name,
            player_id=player_id,
            teams=teams,
            user_id=user_id,
            puzzle_date=puzzle_date,
            hard_mode=hard_mode,
        )
    except SessionError as exc:
        return _session_error(exc, 409 if "already played" in str(exc) else 400)

    return jsonify(_with_quota(public_view(session), quota)), 201


@app.route("/api/game/archive", methods=["GET"])
def api_game_archive():
    """Past dailies. Visible to anyone signed in; playable only by owners.

    The list is deliberately not gated. Somebody deciding whether to buy should
    be able to see how much is there, and a list of dates is not the product --
    the puzzles are. What is gated is starting one.

    No unplayed puzzle's player name is included. That is the answer, and a
    listing endpoint is an easy place to give away ninety of them at once.
    """
    try:
        user_id = _current_user_id()
    except AuthError as exc:
        return _session_error(exc, 401)

    if puzzles_repo is None:
        return jsonify({"puzzles": [], "unlocked": False, "available": False})

    today = today_eastern()
    earliest, latest = archive.playable_range(today)
    scheduled = puzzles_repo.scheduled_between(earliest, latest)

    played = session_store.played_dates(user_id, archive.MODE) if user_id else set()

    return jsonify(
        {
            "puzzles": archive.listing(scheduled, played, today),
            "unlocked": bool(user_id) and entitlements.is_unlimited(user_id),
            "available": True,
            "signed_in": bool(user_id),
        }
    )


@app.route("/api/game/<session_id>", methods=["GET"])
def api_game_get(session_id):
    session = session_store.get(session_id)
    if session is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(session)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/guess", methods=["POST"])
def api_game_guess(session_id):
    existing = session_store.get(session_id)
    if existing is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(existing)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    limited = _rate_limited("game_guess", GUESS_LIMIT, existing.user_id)
    if limited:
        return limited

    body = request.get_json(silent=True) or {}
    try:
        session = submit_guess(
            session_store,
            session_id,
            position=body.get("position"),
            guess=body.get("guess"),
        )
    except SessionNotFound as exc:
        return _session_error(exc, 404)
    except (SessionError, ValueError) as exc:
        return _session_error(exc, 400)

    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/hint", methods=["POST"])
def api_game_hint(session_id):
    existing = session_store.get(session_id)
    if existing is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(existing)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    try:
        session = use_hint(session_store, session_id)
    except SessionNotFound as exc:
        return _session_error(exc, 404)
    except SessionError as exc:
        return _session_error(exc, 400)

    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/hard-mode", methods=["POST"])
def api_game_hard_mode(session_id):
    existing = session_store.get(session_id)
    if existing is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(existing)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    try:
        session = set_hard_mode(session_store, session_id, body.get("enabled", False))
    except SessionNotFound as exc:
        return _session_error(exc, 404)
    except SessionError as exc:
        return _session_error(exc, 400)

    return jsonify(public_view(session))


@app.route("/api/game/<session_id>/abandon", methods=["POST"])
def api_game_abandon(session_id):
    existing = session_store.get(session_id)
    if existing is None:
        return jsonify({"error": "no such session"}), 404

    try:
        denied = _authorise(existing)
    except AuthError as exc:
        return _session_error(exc, 401)
    if denied:
        return denied

    try:
        session = abandon(session_store, session_id)
    except SessionNotFound as exc:
        return _session_error(exc, 404)

    return jsonify(public_view(session))


# ---------------------------------------------------------------------------
# Billing
#
# Fulfilment happens on a signature-verified webhook and nowhere else. The
# browser returning from Checkout proves nothing -- the success URL is
# client-controlled and anyone can visit it.
# ---------------------------------------------------------------------------


@app.route("/api/billing/config", methods=["GET"])
def api_billing_config():
    """Whether to show a buy button, and what the caller already has.

    One request rather than two, because the answer to "can they buy" and "have
    they bought" are needed together and are both cheap.
    """
    try:
        user_id = _current_user_id()
    except AuthError as exc:
        return _session_error(exc, 401)

    owned = bool(user_id) and entitlements.is_unlimited(user_id)
    return jsonify(
        {
            # False when payments are unconfigured, so a deployment without
            # Stripe shows no buy button rather than a broken one.
            "available": stripe_billing.is_configured(config),
            # Why not, when not. A bare False sent an operator to the error
            # tracker to learn that a product id had been pasted where a price
            # id belonged -- something this endpoint knew and was not saying.
            # Names no secret, only which setting is missing or wrong.
            "status": stripe_billing.configuration_status(config),
            "owned": owned,
            # Stated rather than assumed by the client, so the copy and the
            # rule cannot drift apart.
            "free_games_per_day": FREE_GAMES_PER_DAY,
            "signed_in": bool(user_id),
        }
    )


@app.route("/api/billing/checkout", methods=["POST"])
def api_billing_checkout():
    """Start a Checkout session for the signed-in player."""
    try:
        user_id = _current_user_id()
    except AuthError as exc:
        return _session_error(exc, 401)

    if not user_id:
        # Not a failure so much as a precondition: an anonymous purchase would
        # have nothing to attach itself to.
        return jsonify(
            {"error": "Sign in first, so the purchase is attached to your account."}
        ), 401

    limited = _rate_limited("billing_checkout", CHECKOUT_LIMIT, user_id)
    if limited:
        return limited

    if entitlements.is_unlimited(user_id):
        # Refusing is kinder than taking the money and refunding it later.
        return jsonify({"error": "You already have unlimited access."}), 409

    base = config.public_url or request.host_url.rstrip("/")
    try:
        session = stripe_billing.create_checkout_session(
            config,
            user_id,
            success_url=f"{base}/?purchase=success",
            cancel_url=f"{base}/?purchase=cancelled",
        )
    except stripe_billing.BillingError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception:
        logger.exception("could not create a checkout session")
        return jsonify({"error": "Could not start checkout. Try again shortly."}), 502

    return jsonify(session), 201


@app.route("/api/billing/webhook", methods=["POST"])
def api_billing_webhook():
    """Where money actually becomes an entitlement.

    Never rate limited and never blocked by maintenance mode: a rejected webhook
    is a payment event lost, and these arrive during exactly the incident nobody
    is watching.
    """
    try:
        event = stripe_billing.verify_event(
            request.get_data(),
            request.headers.get("Stripe-Signature"),
            config.stripe_webhook_secret,
        )
    except stripe_billing.SignatureError:
        # Logged without the reason: a precise answer is a cheap way to test
        # signatures against us.
        logger.warning("rejected a billing webhook with a bad signature")
        return jsonify({"error": "bad signature"}), 400

    described = stripe_billing.describe(event)
    event_id, action, user_id = (
        described["event_id"],
        described["action"],
        described["user_id"],
    )

    if not event_id:
        return jsonify({"error": "event has no id"}), 400

    if action is None:
        # Acknowledged and ignored. Stripe sends a great deal, and retrying an
        # event we will never act on helps nobody.
        return jsonify({"status": "ignored", "type": described["type"]}), 200

    if not user_id:
        # Recorded rather than dropped: without our reference there is nothing
        # to fulfil, and the reconciliation job should be able to find it.
        payment_events.seen(stripe_billing.PROVIDER, event_id, described["type"], None)
        payment_events.complete(stripe_billing.PROVIDER, event_id, error="no user_id on the event")
        logger.error("billing event carried no user id", extra={"event_id": event_id})
        return jsonify({"status": "unattributable"}), 200

    def fulfil():
        if action == "grant":
            entitlements.grant(user_id, source=stripe_billing.PROVIDER, reference=event_id)
        else:
            entitlements.revoke(user_id, reason=described["reason"])

    try:
        outcome = apply_once(
            payment_events,
            stripe_billing.PROVIDER,
            event_id,
            described["type"],
            fulfil,
        )
    except Exception:
        logger.exception("billing event could not be applied", extra={"event_id": event_id})
        # 500 so Stripe retries. The event is recorded with its error either
        # way, so the reconciliation job can also repair it.
        return jsonify({"error": "could not apply the event"}), 500

    logger.warning(
        "billing event %s", outcome, extra={"event_id": event_id, "billing_action": action}
    )
    return jsonify({"status": outcome}), 200


# ---------------------------------------------------------------------------
# Admin
#
# For the morning a bad puzzle ships. Guarded by a single shared token compared
# in constant time -- not a user role, because there is one operator and building
# an authorisation system for one person is how a weekend disappears.
# ---------------------------------------------------------------------------


def _build_admin(config):
    if not config.use_database:
        return None

    from supabase import create_client

    return AdminOperations(create_client(config.supabase_url, config.supabase_service_key))


admin_ops = _build_admin(config)


def _require_admin():
    """None when authorised, otherwise the response to return."""
    if not is_authorised(token_from_headers(request.headers), config.admin_token):
        # Deliberately identical whether the token is wrong or unconfigured:
        # telling a caller which would confirm an admin surface exists.
        logger.warning("admin request refused", extra={"http_path": request.path})
        return jsonify({"error": "Not authorised."}), 401
    if admin_ops is None:
        return jsonify({"error": "Admin operations need a database."}), 503
    return None


@app.route("/api/admin/puzzles", methods=["GET"])
def api_admin_puzzles():
    denied = _require_admin()
    if denied:
        return denied

    days = min(max(int(request.args.get("days", 7)), 1), 90)
    return jsonify({"puzzles": admin_ops.upcoming_puzzles(today_eastern(), days)})


@app.route("/api/admin/puzzles/<puzzle_date>", methods=["PUT"])
def api_admin_swap_puzzle(puzzle_date):
    denied = _require_admin()
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    player_id = body.get("player_id")
    if not player_id:
        return jsonify({"error": "player_id is required"}), 400

    try:
        result = admin_ops.swap_puzzle(puzzle_date, player_id)
    except AdminError as exc:
        return jsonify({"error": str(exc)}), 400

    # This instance is now holding the puzzle it just replaced. Other instances
    # are covered by the TTL and cannot be reached from here, so the response
    # says how long the swap takes to become universal rather than implying it
    # already is.
    daily_cache.invalidate()

    logger.warning(
        "puzzle swapped",
        extra={"puzzle_date": puzzle_date, "player": result["player"]},
    )
    return jsonify({**result, "effective_within_seconds": DEFAULT_TTL_SECONDS})


@app.route("/api/admin/results/<puzzle_date>/void", methods=["POST"])
def api_admin_void_day(puzzle_date):
    denied = _require_admin()
    if denied:
        return denied

    body = request.get_json(silent=True) or {}
    result = admin_ops.void_day(puzzle_date, body.get("reason"))
    logger.warning("day voided", extra={"puzzle_date": puzzle_date, **result})
    return jsonify(result)


@app.route("/api/admin/results/<puzzle_date>/restore", methods=["POST"])
def api_admin_restore_day(puzzle_date):
    denied = _require_admin()
    if denied:
        return denied

    result = admin_ops.restore_day(puzzle_date)
    logger.warning("day restored", extra={"puzzle_date": puzzle_date, **result})
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
