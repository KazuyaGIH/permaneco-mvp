from pydantic import BaseModel

from app.schemas.common import PreferredName


class StudentProfileUpdate(BaseModel):
    preferred_name: PreferredName
