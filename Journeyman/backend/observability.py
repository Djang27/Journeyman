"""Structured logging and error reporting.

Two bugs in this project were invisible from outside: the leaderboard returned
an empty list for months, and `refresh_leaderboard` was callable by anyone.
Neither raised an exception, so neither would have appeared in an error tracker.
That shapes what is here.

**Logs are structured.** A line per request, as JSON, carrying a request id, the
route, the status and how long it took. Grep-able by a person and queryable by a
machine, which a formatted string is not.

**Every log line carries a request id.** Vercel supplies one per invocation;
otherwise one is generated. Without it, concurrent requests interleave in the
log and nothing can be reconstructed.

**Errors are reported with context, not just a stack.** Which route, which
request id, and never the request body -- a guess is harmless but the habit of
logging bodies is how tokens end up in log aggregators.

Sentry activates when SENTRY_DSN is set and is otherwise absent, so nothing here
requires an account to run.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar

# Set per request and read by the formatter, so no logging call has to pass it.
# A ContextVar rather than a global: concurrent requests would otherwise
# overwrite each other's id and the log would be unreadable exactly when it
# matters.
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

# Header keys that must never reach a log or an error report.
REDACTED_HEADERS = frozenset({"authorization", "cookie", "x-api-key", "apikey", "set-cookie"})


class JsonFormatter(logging.Formatter):
    """One JSON object per line.

    Vercel and most aggregators parse JSON lines into queryable fields; a
    formatted string has to be regex-scraped to answer even "how many 500s".
    """

    def format(self, record):
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": _request_id.get(),
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }

        # Anything passed as extra={"...": ...}, minus logging's own attributes.
        for key, value in getattr(record, "__dict__", {}).items():
            if key not in _LOG_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


_LOG_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
    "taskName",
}


def new_request_id(headers=None):
    """Vercel's invocation id when present, otherwise a fresh one."""
    headers = headers or {}
    supplied = headers.get("x-vercel-id") or headers.get("X-Vercel-Id")
    return supplied or uuid.uuid4().hex[:16]


def set_request_id(request_id):
    _request_id.set(request_id)
    return request_id


def get_request_id():
    return _request_id.get()


def safe_headers(headers):
    """Headers with credentials removed, for logging and error context."""
    return {
        key: ("[redacted]" if key.lower() in REDACTED_HEADERS else value)
        for key, value in dict(headers or {}).items()
    }


def configure_logging(level=logging.INFO, stream=None):
    """JSON to stdout. Replaces handlers so a library cannot re-add a plain one."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    return root


# The reasons error reporting can be off. "false" on its own sent someone
# redeploying to fix a variable that was never the problem, so the endpoint says
# which of these it is.
SENTRY_NO_DSN = "no_dsn"
SENTRY_SDK_MISSING = "sdk_missing"
SENTRY_INIT_FAILED = "init_failed"
SENTRY_ACTIVE = "enabled"


def configure_sentry(dsn, environment="production", release=None):
    """Enable error reporting when a DSN is configured. A no-op otherwise.

    Returns *why* it ended up on or off, not just whether. The three ways this
    can be off look identical from outside -- no DSN reached the process, the
    SDK is not installed, or init itself failed -- and they have completely
    different fixes. Reporting a bare False means guessing between them.
    """
    if not dsn:
        return SENTRY_NO_DSN

    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except ImportError:
        logging.getLogger(__name__).warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return SENTRY_SDK_MISSING

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            integrations=[FlaskIntegration()],
            # Request bodies carry a guess, which is harmless -- but the habit
            # of sending bodies is how tokens end up in someone else's system.
            send_default_pii=False,
            # A fraction, because a busy day should not become a Sentry bill.
            # Enough to see latency shape without paying to record every
            # request.
            traces_sample_rate=0.1,
        )
    except Exception:
        # A malformed DSN raises here. This runs at import time, so letting it
        # propagate would take the whole app down to lose error reporting --
        # exactly backwards.
        logging.getLogger(__name__).exception("sentry init failed")
        return SENTRY_INIT_FAILED

    return SENTRY_ACTIVE


class RequestTimer:
    """Times a request and logs one structured line when it ends."""

    def __init__(self, logger, method, path, request_id):
        self.logger = logger
        self.method = method
        self.path = path
        self.request_id = request_id
        self.started = time.perf_counter()

    def finish(self, status):
        duration_ms = round((time.perf_counter() - self.started) * 1000, 1)

        # Warn on anything the caller was refused, so refusals are visible
        # without turning on debug logging.
        level = logging.WARNING if status >= 400 else logging.INFO
        self.logger.log(
            level,
            "%s %s -> %s",
            self.method,
            self.path,
            status,
            extra={
                "http_method": self.method,
                "http_path": self.path,
                "http_status": status,
                "duration_ms": duration_ms,
            },
        )
        return duration_ms
