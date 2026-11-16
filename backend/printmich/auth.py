"""Optional single-password protection for the web UI plus an API token for automations."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import TYPE_CHECKING

from itsdangerous import BadSignature, URLSafeTimedSerializer

if TYPE_CHECKING:  # pragma: no cover
    from .state import App

COOKIE = "printmich_session"
MAX_AGE = 60 * 60 * 24 * 30
OPEN_PATHS = ("/api/auth/", "/api/health")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, salt_hex, digest_hex = stored.split("$")
        if algo != "scrypt":
            return False
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(digest.hex(), digest_hex)
    except Exception:
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, app: App):
        self.app = app

    def _secret(self) -> str:
        s = self.app.store.raw_settings()
        if not s.session_secret:
            secret = secrets.token_urlsafe(32)
            self.app.store.update_settings(session_secret=secret)
            return secret
        return s.session_secret

    @property
    def enabled(self) -> bool:
        return bool(self.app.cfg.password) or bool(self.app.store.raw_settings().password_hash)

    def check_password(self, password: str) -> bool:
        if self.app.cfg.password:
            return hmac.compare_digest(password.encode(), self.app.cfg.password.encode())
        stored = self.app.store.raw_settings().password_hash
        return bool(stored) and verify_password(password, stored)

    def make_session(self) -> str:
        return URLSafeTimedSerializer(self._secret(), salt="session").dumps({"u": "admin"})

    def valid_session(self, cookie: str | None) -> bool:
        if not cookie:
            return False
        try:
            URLSafeTimedSerializer(self._secret(), salt="session").loads(cookie, max_age=MAX_AGE)
            return True
        except BadSignature:
            return False

    def valid_token(self, token: str | None) -> bool:
        stored = self.app.store.raw_settings().api_token_hash
        return bool(token and stored) and hmac.compare_digest(hash_token(token or ""), stored)

    def allowed(self, path: str, cookie: str | None, authorization: str | None, query_token: str | None) -> bool:
        if not path.startswith("/api/") or path.startswith(OPEN_PATHS):
            return True
        token = None
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        if token and self.valid_token(token):
            return True
        if query_token and self.valid_token(query_token):
            return True
        if not self.enabled:
            return True
        return self.valid_session(cookie)
