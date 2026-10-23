import pytest
from argon2 import PasswordHasher
from sqlalchemy import func, select

from app.core.config import settings
from app.models import StudentProfile, TutorAssignment, User
from app.seed import seed_database


def test_seed_refuses_to_run_outside_demo_mode(db_session, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", False)
    monkeypatch.setattr(settings, "demo_password", "demo-only-test-password")

    with pytest.raises(RuntimeError, match="DEMO_MODE=true"):
        seed_database(db_session)


def test_seed_is_idempotent_and_creates_required_personas(db_session, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    monkeypatch.setattr(settings, "demo_password", "demo-only-test-password")

    seed_database(db_session)
    ana = db_session.scalar(select(User).where(User.email == "ana@example.com"))
    ana.password_hash = PasswordHasher().hash("stale-password")
    db_session.commit()
    seed_database(db_session)

    assert db_session.scalar(select(func.count()).select_from(User)) == 34
    assert db_session.scalar(select(func.count()).select_from(TutorAssignment)) == 30
    ana = db_session.scalar(select(User).where(User.email == "ana@example.com"))
    bruno = db_session.scalar(select(User).where(User.email == "bruno@example.com"))
    ana_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == ana.id))

    assert PasswordHasher().verify(ana.password_hash, "demo-only-test-password")
    assert ana_profile.preferred_name == "Ana"
    assert ana_profile.course == "Administração EAD"
    assert ana_profile.age_band == "25-34"
    assert ana_profile.age_years == 34
    assert ana_profile.work_hours_week == 44
    assert ana_profile.semester == 1
    assert bruno.role == "student"
    assert all(user.email.endswith("@example.com") for user in db_session.scalars(select(User)))
