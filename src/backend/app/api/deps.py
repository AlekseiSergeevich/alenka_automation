from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from src.backend.app.core.config import Settings, get_settings
from src.backend.app.core.security import AuthUser, Role, create_session_token, parse_session_token
from src.backend.app.integrations.saby.client import SabyClient
from src.backend.app.services import SyncOrchestrator
from src.backend.app.services.orchestrator import build_orchestrator


def get_saby_client(settings: Settings = Depends(get_settings)) -> SabyClient:
    return SabyClient(settings=settings)


def get_orchestrator(
    client: SabyClient = Depends(get_saby_client),
) -> SyncOrchestrator:
    return build_orchestrator(client)


def _extract_bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization")
    if not auth:
        return None
    lower = auth.lower()
    if not lower.startswith("bearer "):
        return None
    return auth[7:].strip() or None


def get_current_user_optional(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthUser | None:
    """Returns None when unauthenticated; when auth is disabled, a synthetic admin user."""
    if not settings.auth_enabled:
        return AuthUser(username="dev", role=Role.admin)

    token = _extract_bearer_token(request)
    if not token:
        token = request.cookies.get(settings.session_cookie_name)
    if not token:
        return None
    return parse_session_token(
        settings,
        token,
        max_age=settings.session_max_age_seconds,
    )


async def require_user(
    user: AuthUser | None = Depends(get_current_user_optional),
) -> AuthUser:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


async def require_admin(user: AuthUser = Depends(require_user)) -> AuthUser:
    if user.role != Role.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


def new_session_token(settings: Settings, user: AuthUser) -> str:
    return create_session_token(settings, user)
