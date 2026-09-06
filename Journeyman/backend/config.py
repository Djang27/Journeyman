"""Environment configuration, validated at import time.

Every value here is read once and checked. A missing or malformed variable is a
deployment mistake, and it should fail loudly at startup rather than surfacing
as a confusing error on someone's first game.
"""

import os

from auth import jwks_url_for


class ConfigError(RuntimeError):
    """A required environment variable is missing or unusable."""


def _get(name, default=None, required=False):
    value = os.environ.get(name, default)
    if required and not value:
        raise ConfigError(
            f"{name} is not set. Copy backend/.env.example to backend/.env for local "
            f"development, or set it for this environment in Vercel."
        )
    return value


class Config:
    """Resolved settings. Built lazily so importing the app never fails in tests."""

    def __init__(self, environ=None):
        env = environ if environ is not None else os.environ

        self.supabase_url = env.get("SUPABASE_URL", "")

        # The service role key bypasses row level security entirely -- it is how
        # the server reads puzzles and sessions that no client may see. It must
        # never be exposed to the browser, which is why it has no REACT_APP_
        # prefix: Create React App inlines every REACT_APP_* value into the
        # public JavaScript bundle.
        self.supabase_service_key = env.get("SUPABASE_SERVICE_ROLE_KEY", "")

        # Hosted Supabase projects sign tokens with asymmetric keys, so
        # verification needs only the project's public keys -- derived from the
        # URL above, with no extra variable to set or leak.
        self.jwks_url = jwks_url_for(self.supabase_url)

        # The legacy HS256 shared secret. Only used when there is no JWKS URL,
        # which in practice means the local `supabase start` stack. Never set
        # this alongside a hosted URL: see the note in auth.py about downgrade.
        self.supabase_jwt_secret = env.get("SUPABASE_JWT_SECRET", "")

        # Error reporting activates only when a DSN is present, so nothing here
        # requires a Sentry account to run.
        self.sentry_dsn = env.get("SENTRY_DSN", "")
        self.environment = env.get("VERCEL_ENV") or env.get("ENVIRONMENT") or "development"
        # Vercel exposes the deploy's commit, which is what makes an error report
        # answerable: "which version was this?"
        self.release = env.get("VERCEL_GIT_COMMIT_SHA") or env.get("RELEASE") or None

        # Operator credential. Unset means every admin route is closed, not
        # open: the opposite default is how an admin endpoint ends up reachable
        # on a deployment that never meant to enable one.
        self.admin_token = env.get("ADMIN_TOKEN", "")

        # Stripe. All four are absent by default, and checkout is simply not
        # offered without them -- a deployment that has not configured payments
        # should show no buy button rather than a broken one.
        #
        # The webhook secret is as load-bearing as the API key: without it a
        # payment is taken and never fulfilled, which is worse than not selling.
        self.stripe_secret_key = env.get("STRIPE_SECRET_KEY", "")
        self.stripe_webhook_secret = env.get("STRIPE_WEBHOOK_SECRET", "")
        self.stripe_price_id = env.get("STRIPE_PRICE_ID", "")
        # Where Checkout sends the browser back to. Defaults to the deployment
        # itself; set explicitly when the app is not at the domain root.
        self.public_url = (env.get("PUBLIC_URL") or "").rstrip("/")

        # Deliberate downtime. Since Phase 0 every game start writes a session
        # row, so Postgres being unreachable means the game is unplayable -- this
        # exists to fail honestly during planned work, not to keep playing.
        self.maintenance_mode = (env.get("MAINTENANCE_MODE") or "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        self.maintenance_message = env.get("MAINTENANCE_MESSAGE") or (
            "Journeyman is down for maintenance. Back shortly."
        )

        # Falls back to the in-memory store when Supabase is not configured, so
        # `python app.py` works out of the box for someone cloning the repo.
        self.use_database = bool(self.supabase_url and self.supabase_service_key)

    def require_database(self):
        missing = [
            name
            for name, value in (
                ("SUPABASE_URL", self.supabase_url),
                ("SUPABASE_SERVICE_ROLE_KEY", self.supabase_service_key),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                f"Database access needs {' and '.join(missing)}. See backend/.env.example."
            )


def load_config(environ=None):
    return Config(environ)
