"""Structured logging, request correlation, and redaction.

The value of a log line is whether it can be found and whether it can be trusted
not to contain a credential. Both are testable.
"""

import io
import json
import logging

import pytest
from observability import (
    JsonFormatter,
    RequestTimer,
    configure_logging,
    configure_sentry,
    get_request_id,
    new_request_id,
    safe_headers,
    set_request_id,
)


@pytest.fixture
def captured():
    """A logger writing JSON lines into a buffer."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("test.observability")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, stream


def lines(stream):
    return [json.loads(line) for line in stream.getvalue().strip().splitlines() if line]


class TestJsonFormatter:
    def test_every_line_is_valid_json(self, captured):
        logger, stream = captured
        logger.info("hello")
        assert lines(stream)[0]["message"] == "hello"

    def test_it_carries_the_level_and_logger(self, captured):
        logger, stream = captured
        logger.warning("careful")
        entry = lines(stream)[0]
        assert entry["level"] == "WARNING"
        assert entry["logger"] == "test.observability"

    def test_extra_fields_become_queryable_keys(self, captured):
        """The point of structured logs: "how many 500s" is a query, not a regex."""
        logger, stream = captured
        logger.info("done", extra={"http_status": 500, "duration_ms": 12.5})
        entry = lines(stream)[0]
        assert entry["http_status"] == 500
        assert entry["duration_ms"] == 12.5

    def test_an_exception_is_included(self, captured):
        logger, stream = captured
        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("it broke")
        assert "ValueError: boom" in lines(stream)[0]["exception"]

    def test_unserialisable_values_do_not_lose_the_line(self, captured):
        """A logging call must never be the thing that breaks a request."""
        logger, stream = captured
        logger.info("odd", extra={"thing": object()})
        assert lines(stream)[0]["message"] == "odd"


class TestRequestCorrelation:
    def test_vercels_invocation_id_is_used_when_present(self):
        assert new_request_id({"x-vercel-id": "iad1::abc123"}) == "iad1::abc123"

    def test_one_is_generated_otherwise(self):
        assert new_request_id({}) and new_request_id({}) != new_request_id({})

    def test_the_id_appears_on_every_line(self, captured):
        """Without it, concurrent requests interleave and nothing can be read."""
        logger, stream = captured
        set_request_id("req-abc")
        logger.info("first")
        logger.info("second")
        assert {entry["request_id"] for entry in lines(stream)} == {"req-abc"}

    def test_it_can_be_read_back(self):
        set_request_id("req-xyz")
        assert get_request_id() == "req-xyz"


class TestRedaction:
    @pytest.mark.parametrize(
        "header", ["Authorization", "authorization", "Cookie", "apikey", "X-API-Key"]
    )
    def test_credentials_are_redacted(self, header):
        assert safe_headers({header: "secret-value"})[header] == "[redacted]"

    def test_ordinary_headers_survive(self):
        assert safe_headers({"User-Agent": "curl/8"})["User-Agent"] == "curl/8"

    def test_a_bearer_token_never_reaches_a_log(self):
        cleaned = safe_headers({"Authorization": "Bearer eyJhbGciOi.secret.value"})
        assert "eyJhbGciOi" not in json.dumps(cleaned)


class TestRequestTimer:
    def test_it_logs_one_line_with_the_outcome(self, captured):
        logger, stream = captured
        RequestTimer(logger, "POST", "/api/game/start", "req-1").finish(201)

        entry = lines(stream)[0]
        assert entry["http_method"] == "POST"
        assert entry["http_path"] == "/api/game/start"
        assert entry["http_status"] == 201
        assert entry["duration_ms"] >= 0

    def test_a_refusal_is_logged_at_warning(self, captured):
        """So refusals are visible without turning on debug logging."""
        logger, stream = captured
        RequestTimer(logger, "POST", "/api/game/start", "req-1").finish(429)
        assert lines(stream)[0]["level"] == "WARNING"

    def test_success_is_not(self, captured):
        logger, stream = captured
        RequestTimer(logger, "GET", "/api/health", "req-1").finish(200)
        assert lines(stream)[0]["level"] == "INFO"


class TestSentry:
    def test_it_stays_off_without_a_dsn(self):
        """Nothing here may require an account to run."""
        assert configure_sentry("") is False
        assert configure_sentry(None) is False


class TestConfigureLogging:
    def test_it_installs_the_json_formatter(self):
        stream = io.StringIO()
        root = configure_logging(stream=stream)
        try:
            assert isinstance(root.handlers[0].formatter, JsonFormatter)
        finally:
            logging.getLogger().handlers = []
