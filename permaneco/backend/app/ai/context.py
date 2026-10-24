import json
import re
import secrets
from pathlib import Path
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.timezone import format_app_datetime
from app.models import (
    Conversation,
    Consent,
    KnowledgeItem,
    Memory,
    Message,
    NextStep,
    Plan,
    SessionSummary,
    StudentProfile,
)

_SYSTEM_TEMPLATE = (Path(__file__).resolve().parents[1] / "prompts" / "mentor_system.md").read_text(
    encoding="utf-8"
)
CANARY = secrets.token_urlsafe(24)
_CONTEXT_TAGS = (
    "tipo_de_conversa",
    "canal",
    "data_e_hora_atual",
    "perfil_do_aluno",
    "memorias",
    "resumo_da_ultima_conversa",
    "proximos_passos",
    "plano_atual",
    "base_de_conhecimento",
    "conversa",
    "memorias_existentes",
    "pedido_de_mudanca",
)
_TAG_PATTERN = re.compile(rf"<\s*/?\s*(?:{'|'.join(_CONTEXT_TAGS)})(?=\s|/?>)", re.IGNORECASE)


def escape_context_text(value: str) -> str:
    return _TAG_PATTERN.sub(lambda match: match.group(0).replace("<", "&lt;"), value)


def _block(name: str, value: str) -> str:
    return f"<{name}>\n{escape_context_text(value)}\n</{name}>"


def _without_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_ids(item)
            for key, item in value.items()
            if key not in {"id", "student_id", "knowledge_id", "source_conversation_id"}
        }
    if isinstance(value, list):
        return [_without_ids(item) for item in value]
    return value


def _memory_context(db: Session, student_id, kind: str) -> list[str]:
    memory_consent = db.scalar(
        select(Consent.id)
        .where(
            Consent.user_id == student_id,
            Consent.consent_type == "memory",
            Consent.accepted.is_(True),
        )
        .limit(1)
    )
    if memory_consent is None:
        return []
    priorities = {
        "checkin": ("dificuldade", "conquista", "rotina", "motivacao", "trabalho"),
        "boas_vindas": ("objetivo", "preferencia", "rotina", "trabalho", "carreira"),
    }
    preferred = priorities.get(kind, ("preferencia", "objetivo", "rotina", "dificuldade"))
    rows = list(
        db.scalars(
            select(Memory)
            .where(Memory.student_id == student_id, Memory.is_active.is_(True))
            .order_by(desc(Memory.updated_at), desc(Memory.created_at))
            .limit(50)
        )
    )
    rank = {category: index for index, category in enumerate(preferred)}
    rows.sort(
        key=lambda row: (
            rank.get(row.category, len(rank)),
            -(row.updated_at or row.created_at).timestamp(),
        )
    )
    return [row.content for row in rows[:15]]


def build_context(
    db: Session,
    conversation: Conversation,
    profile: StudentProfile,
    user_message: str,
    clock: Clock,
) -> tuple[str, list[dict[str, str]]]:
    student_id = conversation.student_id
    profile_data = {
        "nome_preferido": profile.preferred_name,
        "curso": profile.course,
        "semestre": profile.semester,
        "faixa_etaria": profile.age_band,
        "trabalha": profile.works,
        "horas_de_trabalho_semanais": profile.work_hours_week,
        "horas_livres_semanais": profile.free_hours_week,
        "horario_preferido": profile.preferred_time,
        "canal_preferido": profile.preferred_channel,
    }
    memory_values = _memory_context(db, student_id, conversation.kind)
    summary = db.scalar(
        select(SessionSummary)
        .join(Conversation, Conversation.id == SessionSummary.conversation_id)
        .where(
            Conversation.student_id == student_id,
            Conversation.id != conversation.id,
        )
        .order_by(desc(SessionSummary.created_at))
        .limit(1)
    )
    next_steps = list(
        db.scalars(
            select(NextStep)
            .where(NextStep.student_id == student_id, NextStep.completed.is_(False))
            .order_by(desc(NextStep.created_at))
            .limit(3)
        )
    )
    plan = db.scalar(
        select(Plan).where(Plan.student_id == student_id).order_by(desc(Plan.version)).limit(1)
    )
    plan_text = ""
    if plan:
        try:
            plan_text = json.dumps(_without_ids(json.loads(plan.content)), ensure_ascii=False)[
                :3000
            ]
        except (json.JSONDecodeError, TypeError):
            plan_text = plan.content[:1500]

    search_query = func.plainto_tsquery("portuguese", user_message)
    knowledge = list(
        db.scalars(
            select(KnowledgeItem)
            .where(
                KnowledgeItem.is_active.is_(True),
                KnowledgeItem.search_vector.op("@@")(search_query),
            )
            .order_by(desc(func.ts_rank(KnowledgeItem.search_vector, search_query)))
            .limit(3)
        )
    )
    knowledge_values = [
        f"{item.title} [{item.kind}]\n{item.content[:900]}\nFonte: {item.source_url}"
        for item in knowledge
    ]
    blocks = [
        _block("tipo_de_conversa", conversation.kind),
        _block("canal", conversation.channel),
        _block("data_e_hora_atual", format_app_datetime(clock.now())),
        _block("perfil_do_aluno", json.dumps(profile_data, ensure_ascii=False)),
        _block("memorias", "\n".join(memory_values)),
        _block("resumo_da_ultima_conversa", summary.content if summary else ""),
        _block(
            "proximos_passos",
            "\n".join(f"{step.content} {step.due_text or ''}".strip() for step in next_steps),
        ),
        _block("plano_atual", plan_text),
        _block("base_de_conhecimento", "\n\n".join(knowledge_values)),
    ]
    system = _SYSTEM_TEMPLATE.replace("{{CANARY}}", CANARY) + "\n\n" + "\n\n".join(blocks)
    history = list(
        db.scalars(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(desc(Message.created_at))
            .limit(20)
        )
    )
    history.reverse()
    messages = [
        {"role": row.role, "content": escape_context_text(row.content)}
        for row in history
        if row.role in {"user", "assistant"}
    ]
    return system, messages
