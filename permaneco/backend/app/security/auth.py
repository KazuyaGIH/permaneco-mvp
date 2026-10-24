import hashlib
import hmac
import time
from collections import defaultdict, deque
from threading import Lock
from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.dependencies import get_clock
from app.db.session import get_db
from app.models import AuthSession, User

SESSION_COOKIE = "app_session"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
GENERIC_LOGIN_ERROR = "E-mail ou senha inválidos."


def _hash_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window_seconds = window_seconds
        self.attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def allow(self, key: str) -> bool:
        with self._lock:
            now = time.monotonic()
            bucket = self.attempts[key]
            while bucket and now - bucket[0] >= self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.limit:
                return False
            bucket.append(now)
            return True


login_rate_limiter = InMemoryRateLimiter(limit=30, window_seconds=60)


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária."
        )
    session_record = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == _hash_token(token))
    )
    if not session_record or session_record.expires_at <= clock.now():
        if session_record:
            db.delete(session_record)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária."
        )
    user = db.get(User, session_record.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticação necessária."
        )
    request.state.session_record = session_record
    return user


def require_csrf(
    request: Request,
    user: User = Depends(get_current_user),
) -> None:
    del user
    session_record = request.state.session_record
    cookie_token = request.cookies.get(CSRF_COOKIE, "")
    header_token = request.headers.get(CSRF_HEADER, "")
    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
        or not hmac.compare_digest(_hash_token(cookie_token), session_record.csrf_token_hash)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token CSRF inválido.")


def require_role(*roles: str) -> Callable:
    def role_dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Acesso não permitido."
            )
        return user

    return role_dependency
