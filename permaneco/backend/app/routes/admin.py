from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import AuditLog, User
from app.schemas.auth import UserResponse
from app.security.auth import require_role

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserResponse])
def list_users(
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> list[User]:
    users = list(db.scalars(select(User).order_by(User.email)))
    db.add(
        AuditLog(
            actor_id=user.id,
            action="list_accounts",
            target_type="account_collection",
        )
    )
    db.commit()
    return users
