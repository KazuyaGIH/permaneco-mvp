import json
import re
import uuid
from difflib import SequenceMatcher
from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.ai.plans import build_plan_prompt, current_plan, generate_valid_plan
from app.ai.providers.base import ProviderUnavailableError, StructuredOutputError
from app.ai.providers.factory import get_provider
from app.core.clock import DemoClock
from app.core.config import settings
from app.db.session import SessionLocal
from app.models import (
    Checkin,
    Consent,
    Conversation,
    KnowledgeItem,
    Memory,
    Message,
    NextStep,
    Plan,
    PlanProposal,
    SessionSummary,
    StudentProfile,
    TokenUsage,
)
from app.schemas.ai import MemoryExtraction, SummarySchema
from app.security.sanitize import detect_prompt_injection, sanitize_message

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
_MEMORY_INSTRUCTION = re.compile(
    r"\b(?:a partir de agora|ignore|prompt|sistema|instrução|instrução|regra)\b",
    re.IGNORECASE,
)
_FIRST_PERSON = re.compile(r"\b(?:eu|meu|minha|meus|minhas)\b", re.IGNORECASE)
_SENSITIVE_REQUEST = re.compile(r"\b(?:lembre|lembre-se|guarde|salve)\b", re.IGNORECASE)


def _clock(db: Session) -> DemoClock:
    return DemoClock(SessionLocal, enabled=settings.demo_mode)


def _transcript(db: Session, conversation_id) -> str:
    rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return "\n".join(f"{row.role}: {row.content}" for row in rows)


def _profile_values(profile: StudentProfile) -> dict:
    return {
        "nome_preferido": profile.preferred_name,
        "curso": profile.course,
        "semestre": profile.semester,
        "horas_livres_semanais": profile.free_hours_week,
        "horas_de_trabalho_semanais": profile.work_hours_week,
        "trabalha": profile.works,
    }


def _can_use_model(db: Session, student_id, day) -> bool:
    usage = db.scalar(
        select(TokenUsage).where(TokenUsage.student_id == student_id, TokenUsage.day == day)
    )
    return (usage.tokens if usage else 0) < settings.max_daily_tokens_per_student


def _record_estimated_usage(db: Session, student_id, day, prompt: str, result: str) -> None:
    estimated = max(1, (len(prompt) + len(result)) // 4)
    usage = db.scalar(
        select(TokenUsage).where(TokenUsage.student_id == student_id, TokenUsage.day == day)
    )
    if usage:
        usage.tokens += estimated
    else:
        db.add(TokenUsage(student_id=student_id, day=day, tokens=estimated))


def _extract_memory(
    db: Session,
    provider,
    conversation: Conversation,
    profile: StudentProfile,
    transcript: str,
    day,
) -> None:
    accepted = db.scalar(
        select(Consent.id)
        .where(
            Consent.user_id == conversation.student_id,
            Consent.consent_type == "memory",
            Consent.accepted.is_(True),
        )
        .limit(1)
    )
    if not accepted or not _can_use_model(db, conversation.student_id, day):
        return
    existing = list(
        db.scalars(
            select(Memory).where(
                Memory.student_id == conversation.student_id,
                Memory.is_active.is_(True),
            )
        )
    )
    prompt_template = (PROMPTS_DIR / "memory_extractor.md").read_text(encoding="utf-8")
    prompt = "\n\n".join(
        (
            f"<conversa>\n{transcript}\n</conversa>",
            f"<memorias_existentes>\n{json.dumps([item.content for item in existing], ensure_ascii=False)}\n</memorias_existentes>",
            f"<perfil_do_aluno>\n{json.dumps(_profile_values(profile), ensure_ascii=False)}\n</perfil_do_aluno>",
        )
    )
    try:
        result = provider.generate_json(prompt_template, prompt, MemoryExtraction, model="fast")
    except (ProviderUnavailableError, StructuredOutputError):
        return
    _record_estimated_usage(db, conversation.student_id, day, prompt, result.model_dump_json())
    user_text = "\n".join(
        row.content
        for row in db.scalars(
            select(Message).where(
                Message.conversation_id == conversation.id,
                Message.role == "user",
            )
        )
    )
    asked_to_remember = bool(_SENSITIVE_REQUEST.search(user_text))
    for candidate in result.memories:
        if (
            candidate.is_instruction
            or detect_prompt_injection(candidate.fact)
            or _MEMORY_INSTRUCTION.search(candidate.fact)
            or _FIRST_PERSON.search(candidate.fact)
            or len(candidate.fact) > 200
        ):
            continue
        sanitized = sanitize_message(candidate.fact)
        if sanitized.redaction_flags:
            continue
        if candidate.is_sensitive and not asked_to_remember:
            continue
        match = next(
            (
                item
                for item in existing
                if item.category == candidate.category
                and SequenceMatcher(None, item.content.lower(), candidate.fact.lower()).ratio()
                >= 0.78
            ),
            None,
        )
        if match:
            match.content = candidate.fact
            match.is_sensitive = candidate.is_sensitive
            match.source_conversation_id = conversation.id
            match.updated_at = _clock(db).now()
        else:
            active_count = len([item for item in existing if item.is_active])
            if active_count >= 50:
                oldest = min(existing, key=lambda item: item.updated_at or item.created_at)
                oldest.is_active = False
                existing.remove(oldest)
            memory = Memory(
                student_id=conversation.student_id,
                source_conversation_id=conversation.id,
                content=candidate.fact,
                category=candidate.category,
                is_sensitive=candidate.is_sensitive,
                is_active=True,
            )
            db.add(memory)
            existing.append(memory)


def _save_plan(
    db: Session,
    provider,
    student_id,
    profile: StudentProfile,
    memories: list[str],
    current: Plan | None,
    requested_change: str = "",
    requested_section: str | None = None,
) -> None:
    if not _can_use_model(db, student_id, _clock(db).now().date()):
        return
    knowledge = list(db.scalars(select(KnowledgeItem).where(KnowledgeItem.is_active.is_(True))))
    current_content = current.content if current else ""
    prompt = build_plan_prompt(profile, memories, knowledge, current_content, requested_change)
    system = (PROMPTS_DIR / "plan_generator.md").read_text(encoding="utf-8")
    try:
        plan = generate_valid_plan(provider, system, prompt, profile, db)
        if current and requested_section:
            previous_data = json.loads(current.content)
            new_data = plan.model_dump(mode="json")
            changed_sections = [
                section
                for section in ("estudos", "carreira", "financas")
                if section != requested_section
                and previous_data.get(section) != new_data.get(section)
            ]
            if changed_sections:
                prompt += (
                    "\n\nA validação detectou alteração indevida. Preserve exatamente estas seções: "
                    + ", ".join(changed_sections)
                )
                plan = generate_valid_plan(provider, system, prompt, profile, db)
                if any(
                    json.loads(current.content).get(section)
                    != plan.model_dump(mode="json").get(section)
                    for section in ("estudos", "carreira", "financas")
                    if section != requested_section
                ):
                    return
    except (ProviderUnavailableError, StructuredOutputError, ValueError):
        return
    _record_estimated_usage(db, student_id, _clock(db).now().date(), prompt, plan.model_dump_json())
    latest = current_plan(db, student_id)
    db.add(
        Plan(
            student_id=student_id,
            version=(latest.version + 1) if latest else 1,
            content=plan.model_dump_json(),
            change_summary=plan.change_summary,
        )
    )


def process_conversation_end(conversation_id: str, student_id: str) -> None:
    with SessionLocal() as db:
        conversation = db.get(Conversation, uuid.UUID(conversation_id))
        if not conversation or str(conversation.student_id) != student_id:
            return
        profile = db.scalar(
            select(StudentProfile).where(StudentProfile.user_id == conversation.student_id)
        )
        if not profile:
            return
        clock = _clock(db)
        day = clock.now().date()
        transcript = _transcript(db, conversation.id)
        try:
            provider = get_provider()
        except ProviderUnavailableError:
            return

        if _can_use_model(db, conversation.student_id, day):
            summary_prompt = (PROMPTS_DIR / "session_summary.md").read_text(encoding="utf-8")
            try:
                summary = provider.generate_json(
                    summary_prompt,
                    f"<conversa>\n{transcript}\n</conversa>",
                    SummarySchema,
                    model="fast",
                )
                _record_estimated_usage(
                    db, conversation.student_id, day, transcript, summary.model_dump_json()
                )
                row = db.scalar(
                    select(SessionSummary).where(SessionSummary.conversation_id == conversation.id)
                )
                if row:
                    row.content = summary.summary
                else:
                    db.add(SessionSummary(conversation_id=conversation.id, content=summary.summary))
                old_steps = db.scalars(
                    select(NextStep).where(
                        NextStep.student_id == conversation.student_id,
                        NextStep.completed.is_(False),
                    )
                )
                for step in old_steps:
                    db.delete(step)
                db.add_all(
                    [
                        NextStep(
                            student_id=conversation.student_id,
                            content=step.text,
                            due_text=step.due_text,
                        )
                        for step in summary.next_steps
                    ]
                )
                db.commit()
            except (ProviderUnavailableError, StructuredOutputError):
                db.rollback()

        try:
            _extract_memory(db, provider, conversation, profile, transcript, day)
            db.commit()
        except Exception:
            db.rollback()

        if conversation.kind == "checkin":
            checkin = db.scalar(
                select(Checkin)
                .where(
                    Checkin.student_id == conversation.student_id,
                    Checkin.status == "agendado",
                )
                .order_by(desc(Checkin.scheduled_for))
                .limit(1)
            )
            if checkin:
                checkin.status = "concluido"

        if conversation.kind == "boas_vindas" and current_plan(db, conversation.student_id) is None:
            memories = [
                item.content
                for item in db.scalars(
                    select(Memory).where(
                        Memory.student_id == conversation.student_id,
                        Memory.is_active.is_(True),
                    )
                )
            ]
            try:
                _save_plan(db, provider, conversation.student_id, profile, memories, None)
            except Exception:
                db.rollback()
        db.commit()


def process_plan_proposal(proposal_id: str, student_id: str) -> None:
    with SessionLocal() as db:
        proposal = db.get(PlanProposal, uuid.UUID(proposal_id))
        if not proposal or str(proposal.student_id) != student_id or proposal.status != "confirmed":
            return
        profile = db.scalar(
            select(StudentProfile).where(StudentProfile.user_id == proposal.student_id)
        )
        if not profile:
            return
        memories = [
            item.content
            for item in db.scalars(
                select(Memory).where(
                    Memory.student_id == proposal.student_id,
                    Memory.is_active.is_(True),
                )
            )
        ]
        _save_plan(
            db,
            get_provider(),
            proposal.student_id,
            profile,
            memories,
            current_plan(db, proposal.student_id),
            proposal.change,
            proposal.section,
        )
        db.commit()
