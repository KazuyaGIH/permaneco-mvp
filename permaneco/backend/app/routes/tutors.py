import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.dependencies import get_clock
from app.db.session import get_db
from app.models import AuditLog, StudentIdentity, StudentProfile, TutorAssignment, User
from app.schemas.auth import StudentProfileResponse, TutorStudentResponse
from app.security.auth import require_role

router = APIRouter(prefix="/api/tutor", tags=["tutors"])


def _audit(db: Session, tutor: User, student_id: uuid.UUID, clock: Clock) -> None:
    db.add(
        AuditLog(
            actor_id=tutor.id,
            action="view_student",
            target_type="student",
            target_id=student_id,
            created_at=clock.now(),
        )
    )


@router.get("/students", response_model=list[StudentProfileResponse])
def assigned_students(
    user: User = Depends(require_role("tutor")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> list[StudentProfile]:
    profiles = list(
        db.scalars(
            select(StudentProfile)
            .join(TutorAssignment, TutorAssignment.student_id == StudentProfile.user_id)
            .where(TutorAssignment.tutor_id == user.id)
            .order_by(StudentProfile.preferred_name)
        )
    )
    for profile in profiles:
        _audit(db, user, profile.user_id, clock)
    db.commit()
    return profiles


@router.get("/students/{student_id}", response_model=TutorStudentResponse)
def assigned_student(
    student_id: uuid.UUID,
    user: User = Depends(require_role("tutor")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> TutorStudentResponse:
    assignment = db.scalar(
        select(TutorAssignment).where(
            TutorAssignment.tutor_id == user.id,
            TutorAssignment.student_id == student_id,
        )
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Estudante não encontrado.")
    row = db.execute(
        select(StudentProfile, StudentIdentity)
        .join(StudentIdentity, StudentIdentity.user_id == StudentProfile.user_id)
        .where(StudentProfile.user_id == student_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Estudante não encontrado.")
    profile, identity = row
    _audit(db, user, profile.user_id, clock)
    db.commit()
    return TutorStudentResponse(
        user_id=profile.user_id,
        preferred_name=profile.preferred_name,
        course=profile.course,
        semester=profile.semester,
        age_band=profile.age_band,
        works=profile.works,
        work_hours_week=profile.work_hours_week,
        free_hours_week=profile.free_hours_week,
        preferred_time=profile.preferred_time,
        preferred_channel=profile.preferred_channel,
        full_name=identity.full_name,
        contact_email=identity.contact_email,
        phone=identity.phone,
    )
