from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import StudentProfile, User
from app.schemas.auth import StudentProfileResponse
from app.security.auth import require_role

router = APIRouter(prefix="/api/me", tags=["students"])


@router.get("/profile", response_model=StudentProfileResponse)
def own_profile(
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> StudentProfile:
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    return profile
