"""Session cookies and bearer tokens for minimal multi-user auth."""

from __future__ import annotations

import enum
import secrets
from dataclasses import dataclass

import bcrypt
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from src.backend.app.core.config import Settings


class Role(str, enum.Enum):
    viewer = "viewer"
    admin = "admin"


@dataclass(frozen=True, slots=True)
class AuthUser:
    username: str
    role: Role


def _serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret, salt="cf-auth")


def create_session_token(settings: Settings, user: AuthUser) -> str:
    """Signed token (cookie value or Bearer value)."""
    ser = _serializer(settings.session_secret)
    return ser.dumps({"u": user.username, "r": user.role.value})


def parse_session_token(settings: Settings, token: str, *, max_age: int | None = None) -> AuthUser | None:
    ser = _serializer(settings.session_secret)
    try:
        raw = ser.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(raw, dict):
        return None
    username = raw.get("u")
    role_s = raw.get("r")
    if not isinstance(username, str) or not username:
        return None
    try:
        role = Role(role_s)
    except ValueError:
        return None
    return AuthUser(username=username, role=role)


def verify_password(plain: str, password_hash: str) -> bool:
    if not plain or not password_hash:
        return False
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        return False


def resolve_user_from_credentials(settings: Settings, username: str, password: str) -> AuthUser | None:
    """Match username/password against configured bcrypt hashes."""
    u = username.strip()
    if not u or not password:
        return None

    if settings.auth_admin_username and u == settings.auth_admin_username:
        if verify_password(password, settings.auth_admin_password_hash or ""):
            return AuthUser(username=u, role=Role.admin)

    if settings.auth_viewer_username and u == settings.auth_viewer_username:
        if verify_password(password, settings.auth_viewer_password_hash or ""):
            return AuthUser(username=u, role=Role.viewer)

    return None


def generate_secret_key() -> str:
    """Use in docs / ops to set SESSION_SECRET."""
    return secrets.token_urlsafe(32)
