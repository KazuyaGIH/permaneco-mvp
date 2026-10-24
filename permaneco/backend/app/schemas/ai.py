from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ConsentSubmission(BaseModel):
    age_confirmed: bool
    memory_accepted: bool = False
    voice_accepted: bool = False
    risk_protocol_accepted: bool


class ConversationCreate(BaseModel):
    kind: Literal["boas_vindas", "livre", "checkin"]


class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class PlanBlock(BaseModel):
    day: str = Field(min_length=1, max_length=20)
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")
    activity: str = Field(min_length=1, max_length=160)


class StudiesPlan(BaseModel):
    weekly_blocks: list[PlanBlock]
    priorities: list[str] = Field(max_length=3)
    exam_strategy: str = Field(max_length=500)


class CareerPath(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    steps: list[str] = Field(max_length=3)
    knowledge_ids: list[str] = Field(default_factory=list)


class CareerPlan(BaseModel):
    paths: list[CareerPath] = Field(min_length=2, max_length=3)


class PlanAid(BaseModel):
    knowledge_id: str = Field(min_length=1, max_length=120)


class FinancePlan(BaseModel):
    monthly_income: float | None = None
    fixed_expenses: float | None = None
    tuition: float | None = None
    balance: float | None = None
    actions: list[str] = Field(max_length=3)
    auxilios: list[PlanAid]


class PlanSchema(BaseModel):
    estudos: StudiesPlan
    carreira: CareerPlan
    financas: FinancePlan
    change_summary: str = Field(max_length=300)


class SummaryStep(BaseModel):
    text: str = Field(min_length=1, max_length=120)
    due_text: str | None = Field(default=None, max_length=40)


class SummarySchema(BaseModel):
    summary: str = Field(max_length=400)
    next_steps: list[SummaryStep] = Field(max_length=3)


class MemoryCandidate(BaseModel):
    category: Literal[
        "rotina",
        "trabalho",
        "objetivo",
        "motivacao",
        "dificuldade",
        "conquista",
        "preferencia",
        "financas",
        "carreira",
        "rede_de_apoio",
    ]
    fact: str = Field(min_length=1, max_length=200)
    is_sensitive: bool = False
    is_instruction: bool = False


class MemoryExtraction(BaseModel):
    memories: list[MemoryCandidate]


class ConversationMessageResponse(BaseModel):
    role: str
    content: str
    created_at: datetime
