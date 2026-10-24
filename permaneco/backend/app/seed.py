import random
from datetime import timedelta

from argon2 import PasswordHasher
from faker import Faker
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import DemoClock
from app.core.config import settings
from app.db.session import SessionLocal
from app.knowledge import load_knowledge
from app.models import (
    AppSetting,
    DemoClockSetting,
    StudentIdentity,
    StudentProfile,
    TutorAssignment,
    User,
)

SEED = 20250314
COURSES = [
    "Administração EAD",
    "Gestão de Recursos Humanos EAD",
    "Pedagogia EAD",
    "Ciências Contábeis EAD",
    "Logística EAD",
]


def _reset_demo_credentials(user: User, password_hash: str) -> None:
    user.password_hash = password_hash
    user.failed_login_attempts = 0
    user.locked_until = None


def seed_database(db: Session) -> None:
    if not settings.demo_mode:
        raise RuntimeError("A carga sintética só pode ser executada com DEMO_MODE=true.")
    if not settings.demo_password:
        raise RuntimeError("Configure DEMO_PASSWORD para criar as contas de demonstração.")

    Faker.seed(SEED)
    random.seed(SEED)
    fake = Faker("pt_BR")
    password_hash = PasswordHasher().hash(settings.demo_password)
    tutor_users = []
    for index in range(1, 4):
        tutor_email = f"tutor{index}@example.com"
        tutor = db.scalar(select(User).where(User.email == tutor_email))
        if not tutor:
            tutor = User(email=tutor_email, password_hash=password_hash, role="tutor")
            db.add(tutor)
            db.flush()
        else:
            _reset_demo_credentials(tutor, password_hash)
        tutor_users.append(tutor)

    admin = db.scalar(select(User).where(User.email == "admin@example.com"))
    if not admin:
        db.add(User(email="admin@example.com", password_hash=password_hash, role="admin"))
    else:
        _reset_demo_credentials(admin, password_hash)

    clock = DemoClock(SessionLocal, enabled=True)
    enrollment_date = (clock.now() - timedelta(days=45)).date()
    for index in range(30):
        email = (
            ["ana@example.com", "bruno@example.com"][index]
            if index < 2
            else f"student{index + 1:02d}@example.com"
        )
        user = db.scalar(select(User).where(User.email == email))
        if user:
            _reset_demo_credentials(user, password_hash)
            continue
        user = User(email=email, password_hash=password_hash, role="student")
        db.add(user)
        db.flush()
        is_ana = index == 0
        is_bruno = index == 1
        preferred_name = "Ana" if is_ana else "Bruno" if is_bruno else fake.first_name()
        full_name = "Ana Martins" if is_ana else "Bruno Oliveira" if is_bruno else fake.name()
        works = True if is_ana or is_bruno else random.random() < 0.8
        work_hours = 44 if is_ana else 40 if is_bruno else random.choice([30, 36, 40, 44])
        course = "Administração EAD" if is_ana else random.choice(COURSES)
        age_years = 34 if is_ana else 29 if is_bruno else random.randint(25, 54)
        age_band = "25-34" if age_years <= 34 else "35-44" if age_years <= 44 else "45-54"
        db.add(
            StudentIdentity(
                user_id=user.id,
                full_name=full_name,
                contact_email=email,
                phone="00000000000",
            )
        )
        db.add(
            StudentProfile(
                user_id=user.id,
                preferred_name=preferred_name,
                course=course,
                semester=1,
                enrollment_date=enrollment_date,
                age_band=age_band,
                age_years=age_years,
                works=works,
                work_hours_week=work_hours if works else None,
                free_hours_week=6 if is_ana else random.choice([4, 6, 8, 10]),
                preferred_time="noite",
                preferred_channel="texto",
                cadence_phase="initial",
                experiment_group=None,
            )
        )
        db.add(
            TutorAssignment(tutor_id=tutor_users[index % len(tutor_users)].id, student_id=user.id)
        )

    if not db.scalar(select(DemoClockSetting).limit(1)):
        db.add(DemoClockSetting(offset_seconds=0))
    if not db.scalar(select(AppSetting).where(AppSetting.setting_key == "checkin_policy")):
        db.add(
            AppSetting(
                setting_key="checkin_policy", value={"loaded_from": "config/checkin_policy.yaml"}
            )
        )
    load_knowledge(db)
    db.commit()


def main() -> None:
    with SessionLocal() as db:
        seed_database(db)
    print("Carga sintética concluída.")


if __name__ == "__main__":
    main()
