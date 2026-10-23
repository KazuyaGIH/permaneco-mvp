from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.models import (
    Checkin,
    KnowledgeItem,
    NextStep,
    PlanProposal,
    RiskAlert,
    SecurityEvent,
    StudentProfile,
)


class StrictArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchKnowledgeArguments(StrictArguments):
    query: str = Field(min_length=2, max_length=200)


class NextStepItem(StrictArguments):
    text: str = Field(min_length=1, max_length=160)
    due_text: str | None = Field(default=None, max_length=40)


class UpdateNextStepsArguments(StrictArguments):
    steps: list[NextStepItem] = Field(max_length=3)


class ProposePlanChangeArguments(StrictArguments):
    section: Literal["estudos", "carreira", "financas"]
    change: str = Field(min_length=1, max_length=1000)


class RescheduleCheckinArguments(StrictArguments):
    datetime: datetime


class FlagConcernArguments(StrictArguments):
    level: Literal["alto", "crise"]
    category: str = Field(min_length=2, max_length=64)
    rationale: str = Field(min_length=1, max_length=500)


class EndCheckinArguments(StrictArguments):
    pass


TOOL_SCHEMAS: dict[str, type[StrictArguments]] = {
    "search_knowledge": SearchKnowledgeArguments,
    "update_next_steps": UpdateNextStepsArguments,
    "propose_plan_change": ProposePlanChangeArguments,
    "reschedule_checkin": RescheduleCheckinArguments,
    "flag_concern": FlagConcernArguments,
    "end_checkin": EndCheckinArguments,
}

TOOL_DESCRIPTIONS = {
    "search_knowledge": "Busca conteúdo curado e verificado da base institucional.",
    "update_next_steps": "Substitui os próximos passos abertos por até três passos curtos.",
    "propose_plan_change": "Cria uma proposta de mudança no plano para aprovação do estudante.",
    "reschedule_checkin": "Reagenda o próximo check-in dentro da cadência atual.",
    "flag_concern": "Registra uma preocupação para apoio humano.",
    "end_checkin": "Encerra o check-in aberto, se houver.",
}


def tool_specs() -> list[dict]:
    return [
        {
            "name": name,
            "description": TOOL_DESCRIPTIONS[name],
            "parameters": schema.model_json_schema(),
        }
        for name, schema in TOOL_SCHEMAS.items()
    ]


def _security_event(db: Session, student_id, event_type: str, metadata: dict) -> None:
    db.add(
        SecurityEvent(
            actor_id=student_id,
            event_type=event_type,
            metadata_json=metadata,
        )
    )


def execute_tool(
    name: str,
    raw_args: dict,
    db: Session,
    student_id,
    clock: Clock,
) -> dict:
    schema = TOOL_SCHEMAS.get(name)
    if schema is None:
        _security_event(db, student_id, "unknown_tool_call", {"tool": name[:64]})
        return {"error": "tool_not_allowed"}
    try:
        args = schema.model_validate(raw_args)
    except ValidationError:
        _security_event(db, student_id, "invalid_tool_arguments", {"tool": name})
        return {"error": "invalid_arguments"}

    if name == "search_knowledge":
        query = func.plainto_tsquery("portuguese", args.query)
        rows = db.scalars(
            select(KnowledgeItem)
            .where(
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.search_vector.op("@@")(query),
            )
            .order_by(desc(func.ts_rank(KnowledgeItem.search_vector, query)))
            .limit(3)
        )
        return {
            "items": [
                {
                    "slug": item.slug,
                    "kind": item.kind,
                    "title": item.title,
                    "content": item.content[:900],
                    "source_url": item.source_url,
                }
                for item in rows
            ]
        }

    if name == "update_next_steps":
        old_steps = db.scalars(
            select(NextStep).where(NextStep.student_id == student_id, NextStep.completed.is_(False))
        )
        for step in old_steps:
            db.delete(step)
        db.add_all(
            [
                NextStep(
                    student_id=student_id,
                    content=step.text,
                    due_text=step.due_text,
                )
                for step in args.steps
            ]
        )
        return {"updated": len(args.steps)}

    if name == "propose_plan_change":
        proposal = PlanProposal(
            student_id=student_id,
            section=args.section,
            change=args.change,
            status="pending",
        )
        db.add(proposal)
        db.flush()
        return {"proposal_created": True}

    if name == "reschedule_checkin":
        proposed = args.datetime
        if proposed.tzinfo is None:
            proposed = proposed.replace(tzinfo=timezone.utc)
        now = clock.now()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        if proposed <= now:
            return {"rescheduled": False, "reason": "not_future"}
        profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == student_id))
        if profile is None:
            return {"rescheduled": False, "reason": "profile_unavailable"}
        policy_path = Path(__file__).resolve().parents[3] / "config" / "checkin_policy.yaml"
        phases = yaml.safe_load(policy_path.read_text(encoding="utf-8"))["phases"]
        week = max(1, (now.date() - profile.enrollment_date).days // 7 + 1)
        every_days = next(
            (
                phase["every_days"]
                for phase in phases
                if phase["until_week"] is None or week <= phase["until_week"]
            ),
            60,
        )
        next_checkin = db.scalar(
            select(Checkin)
            .where(Checkin.student_id == student_id, Checkin.status == "agendado")
            .order_by(Checkin.scheduled_for)
            .limit(1)
        )
        upper_bound = (
            next_checkin.scheduled_for + timedelta(days=every_days)
            if next_checkin
            else now + timedelta(days=every_days)
        )
        if proposed > upper_bound:
            return {"rescheduled": False, "reason": "outside_cadence"}
        if next_checkin:
            next_checkin.scheduled_for = proposed
            next_checkin.due_at = proposed + timedelta(hours=48)
        else:
            db.add(
                Checkin(
                    student_id=student_id,
                    scheduled_for=proposed,
                    due_at=proposed + timedelta(hours=48),
                    status="agendado",
                )
            )
        return {"rescheduled": True}

    if name == "flag_concern":
        active_alerts = db.scalars(
            select(RiskAlert).where(RiskAlert.student_id == student_id, RiskAlert.status == "open")
        )
        existing = next(
            (alert for alert in active_alerts if args.category in (alert.categories or [])),
            None,
        )
        if existing:
            existing.level = args.level
            existing.summary = args.rationale
        else:
            db.add(
                RiskAlert(
                    student_id=student_id,
                    level=args.level,
                    categories=[args.category],
                    source="model",
                    status="open",
                    summary=args.rationale,
                )
            )
        return {"concern_flagged": True}

    if name == "end_checkin":
        checkin = db.scalar(
            select(Checkin)
            .where(Checkin.student_id == student_id, Checkin.status == "agendado")
            .order_by(desc(Checkin.scheduled_for))
            .limit(1)
        )
        if checkin:
            checkin.status = "concluido"
        return {"ended": checkin is not None}

    return {"error": "tool_not_allowed"}
