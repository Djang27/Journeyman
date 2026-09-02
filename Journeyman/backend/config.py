"""Environment configuration, validated at import time.

Every value here is read once and checked. A missing or malformed variable is a
deployment mistake, and it should fail loudly at startup rather than surfacing
as a confusing error on someone's first game.
"""

import os


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

        # Verifies access tokens locally, so identifying a player costs no
        # network round trip. Supabase Dashboard -> Settings -> API -> JWT
        # Secret. Without it every token is refused: the server fails closed
        # rather than trusting whoever is asking.
        self.supabase_jwt_secret = env.get("SUPABASE_JWT_SECRET", "")

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
