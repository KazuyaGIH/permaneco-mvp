from datetime import date

from argon2 import PasswordHasher

from app.models import StudentIdentity, StudentProfile, User

TEST_PASSWORD = "synthetic-test-password"


def create_user(db, email: str, role: str, preferred_name: str | None = None) -> User:
    user = User(email=email, password_hash=PasswordHasher().hash(TEST_PASSWORD), role=role)
    db.add(user)
    db.flush()
    if role == "student":
        db.add(
            StudentIdentity(
                user_id=user.id,
                full_name=f"Pessoa Sintética {preferred_name or 'Estudante'}",
                contact_email=email,
                phone="00000000000",
            )
        )
        db.add(
            StudentProfile(
                user_id=user.id,
                preferred_name=preferred_name or "Estudante",
                course="Administração EAD",
                semester=1,
                enrollment_date=date(2025, 2, 1),
                age_band="25-34",
                age_years=30,
                works=True,
                work_hours_week=40,
                free_hours_week=8,
                preferred_time="noite",
                preferred_channel="texto",
            )
        )
        db.flush()
    return user


def login(client, email: str) -> None:
    response = client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200
