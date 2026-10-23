import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.config import settings
from app.core.dependencies import get_clock
from app.db.session import get_db
from app.models import AuthSession, User
from app.schemas.auth import LoginRequest, UserResponse
from app.security.auth import (
    CSRF_COOKIE,
    GENERIC_LOGIN_ERROR,
    SESSION_COOKIE,
    _hash_token,
    get_current_user,
    login_rate_limiter,
    require_csrf,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
password_hasher = PasswordHasher()
dummy_password_hash = password_hasher.hash("synthetic-dummy-password")


def _password_matches(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


@router.post("/login", response_model=UserResponse)
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> User:
    client_ip = request.client.host if request.client else "unknown"
    email = str(credentials.email).strip().lower()
    if not login_rate_limiter.allow(f"ip:{client_ip}") or not login_rate_limiter.allow(
        f"email:{email}"
    ):
        raise HTTPException(
            status_code=429, detail="Muitas tentativas. Tente novamente mais tarde."
        )
    user = db.scalar(select(User).where(User.email == email))
    now = clock.now()
    if not user:
        _password_matches(credentials.password, dummy_password_hash)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)
    if user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)
    if not user.is_active or not _password_matches(credentials.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=GENERIC_LOGIN_ERROR)

    user.failed_login_attempts = 0
    user.locked_until = None
    session_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    session_record = AuthSession(
        user_id=user.id,
        token_hash=_hash_token(session_token),
        csrf_token_hash=_hash_token(csrf_token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
    )
    db.add(session_record)
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 60 * 60,
        path="/",
    )
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.session_ttl_hours * 60 * 60,
        path="/",
    )
    return user


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    db.delete(request.state.session_record)
    db.commit()
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", secure=settings.cookie_secure, httponly=False, samesite="lax"
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
