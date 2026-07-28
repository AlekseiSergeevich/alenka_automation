"""Login, logout, and current user (cookie + Bearer token)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from src.backend.app.api.deps import new_session_token, require_user
from src.backend.app.core.config import Settings, get_settings
from src.backend.app.core.security import AuthUser, resolve_user_from_credentials

router = APIRouter()


class LoginBody(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    username: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


from datetime import datetime, timedelta

_FAILED_LOGINS: dict[str, dict] = {}
MAX_FAILED_ATTEMPTS = 10
LOCKOUT_DURATION = timedelta(minutes=15)

@router.post("/auth/login", response_model=LoginResponse)
async def login(
    body: LoginBody,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> LoginResponse:
    if not settings.auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Authentication is disabled",
        )

    u = body.username.strip()
    now = datetime.now()

    record = _FAILED_LOGINS.get(u)
    if record and record.get("lockout_until"):
        if now < record["lockout_until"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Слишком много неудачных попыток. Попробуйте позже.",
            )
        else:
            _FAILED_LOGINS[u] = {"count": 0, "lockout_until": None}

    user = resolve_user_from_credentials(settings, body.username, body.password)
    if user is None:
        if u not in _FAILED_LOGINS:
            _FAILED_LOGINS[u] = {"count": 1, "lockout_until": None}
        else:
            _FAILED_LOGINS[u]["count"] += 1

        if _FAILED_LOGINS[u]["count"] >= MAX_FAILED_ATTEMPTS:
            _FAILED_LOGINS[u]["lockout_until"] = now + LOCKOUT_DURATION
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Слишком много неудачных попыток. Попробуйте позже.",
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if u in _FAILED_LOGINS:
        _FAILED_LOGINS.pop(u, None)

    token = new_session_token(settings, user)
    max_age = settings.session_max_age_seconds

    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path="/",
    )

    return LoginResponse(
        access_token=token,
        expires_in=max_age,
        user=UserOut(username=user.username, role=user.role.value),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.auth_enabled:
        return
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
    )


@router.get("/auth/me", response_model=UserOut)
async def me(user: AuthUser = Depends(require_user)) -> UserOut:
    return UserOut(username=user.username, role=user.role.value)
