from datetime import timedelta
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.db.session import engine
from app.models import AuditLog, AuthSession, TutorAssignment
from app.security.auth import _hash_token
from tests.helpers import TEST_PASSWORD, create_user, login
from tests.conftest import FIXED_NOW


def test_student_profile_is_always_derived_from_session(client, db_session):
    own_user = create_user(db_session, "student-a@example.com", "student", "Ana")
    other_user = create_user(db_session, "student-b@example.com", "student", "Bruna")
    db_session.commit()

    login(client, own_user.email)
    response = client.get(f"/api/me/profile?student_id={other_user.id}")

    assert response.status_code == 200
    assert response.json()["user_id"] == str(own_user.id)
    assert response.json()["preferred_name"] == "Ana"


def test_tutor_only_lists_assigned_students_and_audits_access(client, db_session):
    tutor = create_user(db_session, "tutor@example.com", "tutor")
    assigned = create_user(db_session, "assigned@example.com", "student", "Ana")
    unassigned = create_user(db_session, "unassigned@example.com", "student", "Bruna")
    db_session.add(TutorAssignment(tutor_id=tutor.id, student_id=assigned.id))
    db_session.commit()
    login(client, tutor.email)

    response = client.get("/api/tutor/students")
    detail = client.get(f"/api/tutor/students/{assigned.id}")

    assert response.status_code == 200
    assert [student["user_id"] for student in response.json()] == [str(assigned.id)]
    assert "contact_email" not in response.json()[0]
    assert detail.status_code == 200
    assert detail.json()["contact_email"] == "assigned@example.com"
    assert detail.json()["full_name"] == "Pessoa Sintética Ana"
    assert db_session.scalar(select(AuditLog).where(AuditLog.actor_id == tutor.id)) is not None
    assert db_session.scalar(select(AuditLog).where(AuditLog.target_id == unassigned.id)) is None


def test_tutor_gets_404_for_unassigned_student(client, db_session):
    tutor = create_user(db_session, "tutor@example.com", "tutor")
    student = create_user(db_session, "student@example.com", "student", "Ana")
    db_session.commit()
    login(client, tutor.email)

    response = client.get(f"/api/tutor/students/{student.id}")

    assert response.status_code == 404
    assert db_session.scalar(select(AuditLog)) is None


@pytest.mark.parametrize(
    "role,email", [("student", "student@example.com"), ("tutor", "tutor@example.com")]
)
def test_student_and_tutor_are_forbidden_from_admin(client, db_session, role, email):
    user = create_user(db_session, email, role, "Ana" if role == "student" else None)
    db_session.commit()
    login(client, user.email)
    response = client.get("/api/admin/users")
    assert response.status_code == 403


def test_admin_lists_accounts_without_content_and_audits(client, db_session):
    admin = create_user(db_session, "admin@example.com", "admin")
    create_user(db_session, "student@example.com", "student", "Ana")
    db_session.commit()
    login(client, admin.email)

    response = client.get("/api/admin/users")

    assert response.status_code == 200
    assert {entry["role"] for entry in response.json()} == {"admin", "student"}
    assert all(
        not {"content", "conversation", "memory", "plan"} & entry.keys()
        for entry in response.json()
    )
    assert db_session.scalar(select(AuditLog).where(AuditLog.actor_id == admin.id)) is not None
    for path in ("/api/admin/conversations", "/api/admin/memories", "/api/admin/plans"):
        assert client.get(path).status_code == 404


def test_unauthenticated_access_is_rejected(client):
    assert client.get("/api/me/profile").status_code == 401
    assert client.get("/api/tutor/students").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_csrf_is_required_for_logout(client, db_session):
    student = create_user(db_session, "student@example.com", "student", "Ana")
    db_session.commit()
    login(client, student.email)

    response = client.post("/api/auth/logout")

    assert response.status_code == 403


def test_expired_session_is_rejected(client, db_session):
    user = create_user(db_session, "student@example.com", "student", "Ana")
    raw_token = "expired-session-token"
    db_session.add(
        AuthSession(
            user_id=user.id,
            token_hash=_hash_token(raw_token),
            csrf_token_hash=_hash_token("csrf-token"),
            expires_at=FIXED_NOW - timedelta(seconds=1),
        )
    )
    db_session.commit()
    client.cookies.set("app_session", raw_token)

    assert client.get("/api/auth/me").status_code == 401


def test_login_lockout_after_five_failures(client, db_session):
    user = create_user(db_session, "student@example.com", "student", "Ana")
    db_session.commit()

    statuses = [
        client.post(
            "/api/auth/login", json={"email": user.email, "password": "wrong-password"}
        ).status_code
        for _ in range(5)
    ]
    db_session.refresh(user)

    assert statuses == [401] * 5
    assert user.failed_login_attempts == 5
    assert user.locked_until == FIXED_NOW + timedelta(minutes=settings.login_lock_minutes)
    assert (
        client.post(
            "/api/auth/login", json={"email": user.email, "password": TEST_PASSWORD}
        ).status_code
        == 401
    )


def test_unknown_and_wrong_password_use_same_message(client, db_session):
    create_user(db_session, "known@example.com", "student", "Ana")
    db_session.commit()

    wrong = client.post("/api/auth/login", json={"email": "known@example.com", "password": "wrong"})
    unknown = client.post(
        "/api/auth/login", json={"email": "missing@example.com", "password": "wrong"}
    )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_cookie_flags_and_login_csrf_cookie(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)
    user = create_user(db_session, "student@example.com", "student", "Ana")
    db_session.commit()

    response = client.post("/api/auth/login", json={"email": user.email, "password": TEST_PASSWORD})
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(cookie for cookie in cookies if cookie.startswith("app_session="))
    csrf_cookie = next(cookie for cookie in cookies if cookie.startswith("csrf_token="))

    assert "httponly" in session_cookie.lower()
    assert "secure" in session_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()
    assert "secure" in csrf_cookie.lower()
    assert "samesite=lax" in csrf_cookie.lower()


def test_audit_log_rejects_update_and_delete(client, db_session):
    admin = create_user(db_session, "admin@example.com", "admin")
    db_session.add(
        AuditLog(actor_id=admin.id, action="list_accounts", target_type="account_collection")
    )
    db_session.commit()
    audit_id = db_session.scalar(select(AuditLog.id))

    with pytest.raises(DBAPIError):
        db_session.execute(
            text("UPDATE audit_log SET action = 'changed' WHERE id = :audit_id"),
            {"audit_id": audit_id},
        )
        db_session.commit()
    db_session.rollback()
    with pytest.raises(DBAPIError):
        db_session.execute(
            text("DELETE FROM audit_log WHERE id = :audit_id"), {"audit_id": audit_id}
        )
        db_session.commit()
    db_session.rollback()


def test_preferred_name_validation():
    from pydantic import ValidationError

    from app.schemas.profile import StudentProfileUpdate

    assert StudentProfileUpdate(preferred_name="João D'Ávila").preferred_name == "João D'Ávila"
    assert StudentProfileUpdate(preferred_name="Ana-Maria").preferred_name == "Ana-Maria"
    for invalid_name in ("Ana 2", "<script>", "A" * 41):
        with pytest.raises(ValidationError):
            StudentProfileUpdate(preferred_name=invalid_name)


def test_demo_clock_uses_persisted_offset(db_session):
    from app.core.clock import DemoClock, FixedClock
    from app.models import DemoClockSetting
    from app.db.session import SessionLocal

    db_session.add(DemoClockSetting(offset_seconds=7 * 24 * 60 * 60))
    db_session.commit()
    clock = DemoClock(SessionLocal, base_clock=FixedClock(FIXED_NOW), enabled=True)
    disabled = DemoClock(SessionLocal, base_clock=FixedClock(FIXED_NOW), enabled=False)

    assert clock.now() == FIXED_NOW + timedelta(days=7)
    assert disabled.now() == FIXED_NOW


def test_system_clock_returns_timezone_aware_time():
    from app.core.clock import SystemClock

    assert SystemClock().now().utcoffset() is not None


def test_fastapi_clock_dependency_obeys_demo_mode(monkeypatch):
    from app.core.clock import DemoClock, SystemClock
    from app.core.dependencies import get_clock

    monkeypatch.setattr(settings, "demo_mode", False)
    assert isinstance(get_clock(), SystemClock)
    monkeypatch.setattr(settings, "demo_mode", True)
    assert isinstance(get_clock(), DemoClock)


def test_schema_contains_every_m1_table():
    from sqlalchemy import inspect

    expected = {
        "users",
        "student_identity",
        "student_profile",
        "consents",
        "conversations",
        "messages",
        "memories",
        "session_summaries",
        "plans",
        "next_steps",
        "checkins",
        "risk_alerts",
        "tutor_notes",
        "tutor_assignments",
        "knowledge_items",
        "audit_log",
        "security_events",
        "sessions",
        "app_settings",
        "demo_clock",
    }
    assert expected <= set(inspect(engine).get_table_names())


def test_sensitive_free_text_columns_use_encryption():
    from app.models import (
        KnowledgeItem,
        Memory,
        Message,
        NextStep,
        Plan,
        RiskAlert,
        SessionSummary,
        TutorNote,
    )
    from app.security.crypto import EncryptedText

    encrypted_columns = [
        Message.__table__.c.content,
        Memory.__table__.c.content,
        SessionSummary.__table__.c.content,
        Plan.__table__.c.content,
        NextStep.__table__.c.content,
        RiskAlert.__table__.c.summary,
        RiskAlert.__table__.c.excerpt,
        TutorNote.__table__.c.content,
        KnowledgeItem.__table__.c.content,
    ]
    assert all(isinstance(column.type, EncryptedText) for column in encrypted_columns)


def test_no_datetime_now_calls_outside_clock_module():
    import re
    from pathlib import Path

    app_path = Path(__file__).parents[1] / "app"
    pattern = re.compile(r"datetime\.(?:now|utcnow)\s*\(")
    offenders = [
        path.relative_to(app_path).as_posix()
        for path in app_path.rglob("*.py")
        if path.name != "clock.py" and pattern.search(path.read_text())
    ]
    assert offenders == []
