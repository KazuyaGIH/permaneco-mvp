import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.common import PreferredName


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: str


class StudentProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    preferred_name: PreferredName
    course: str
    semester: int
    age_band: str
    works: bool
    work_hours_week: int | None
    free_hours_week: int | None
    preferred_time: str | None
    preferred_channel: str | None


class TutorStudentResponse(StudentProfileResponse):
    full_name: str
    contact_email: EmailStr
    phone: str | None
