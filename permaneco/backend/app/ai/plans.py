import json
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.ai.context import escape_context_text
from app.ai.providers.base import LLMProvider, StructuredOutputError
from app.core.clock import SystemClock
from app.core.config import settings
from app.core.timezone import format_app_datetime
from app.models import KnowledgeItem, Plan, StudentProfile
from app.schemas.ai import PlanSchema


def validate_plan(plan: PlanSchema, profile: StudentProfile, db: Session) -> None:
    total_minutes = 0
    for block in plan.estudos.weekly_blocks:
        start = datetime.strptime(block.start, "%H:%M")
        end = datetime.strptime(block.end, "%H:%M")
        if end <= start:
            raise ValueError("O horário final de cada bloco deve ser posterior ao inicial.")
        total_minutes += int((end - start).total_seconds() // 60)
    free_hours = profile.free_hours_week or 0
    if total_minutes > free_hours * 60:
        raise ValueError("As horas planejadas excedem as horas livres declaradas.")

    slugs = {slug for path in plan.carreira.paths for slug in path.knowledge_ids}
    slugs.update(item.knowledge_id for item in plan.financas.auxilios)
    if not slugs:
        return
    knowledge = list(
        db.scalars(
            select(KnowledgeItem).where(
                KnowledgeItem.slug.in_(slugs), KnowledgeItem.is_active.is_(True)
            )
        )
    )
    by_slug = {item.slug: item for item in knowledge}
    if slugs - by_slug.keys():
        raise ValueError("O plano referencia conteúdo inexistente ou inativo.")
    for aid in plan.financas.auxilios:
        if by_slug[aid.knowledge_id].kind != "auxilio":
            raise ValueError("O plano referencia um item que não é auxílio.")


def build_plan_prompt(
    profile: StudentProfile,
    memories: list[str],
    knowledge: list[KnowledgeItem],
    current_plan: str = "",
    requested_change: str = "",
    current_time: str | None = None,
) -> str:
    profile_block = {
        "nome_preferido": profile.preferred_name,
        "curso": profile.course,
        "semestre": profile.semester,
        "horas_livres_semanais": profile.free_hours_week,
        "horas_de_trabalho_semanais": profile.work_hours_week,
        "trabalha": profile.works,
        "horario_preferido": profile.preferred_time,
        "fuso_horario": settings.app_timezone,
    }
    knowledge_block = [
        {
            "id": item.slug,
            "tipo": item.kind,
            "titulo": item.title,
            "conteudo": item.content,
            "fonte_url": item.source_url,
        }
        for item in knowledge
    ]
    local_time = current_time or format_app_datetime(SystemClock().now())
    return "\n\n".join(
        (
            f"<data_e_hora_atual>\n{escape_context_text(local_time)}\n</data_e_hora_atual>",
            f"<perfil_do_aluno>\n{escape_context_text(json.dumps(profile_block, ensure_ascii=False))}\n</perfil_do_aluno>",
            f"<memorias>\n{escape_context_text(json.dumps(memories, ensure_ascii=False))}\n</memorias>",
            f"<plano_atual>\n{escape_context_text(current_plan)}\n</plano_atual>",
            f"<pedido_de_mudanca>\n{escape_context_text(requested_change)}\n</pedido_de_mudanca>",
            f"<base_de_conhecimento>\n{escape_context_text(json.dumps(knowledge_block, ensure_ascii=False))}\n</base_de_conhecimento>",
        )
    )


def generate_valid_plan(
    provider: LLMProvider,
    system: str,
    prompt: str,
    profile: StudentProfile,
    db: Session,
) -> PlanSchema:
    last_error = "A validação do plano falhou."
    for attempt in range(2):
        plan = provider.generate_json(
            system,
            prompt if attempt == 0 else f"{prompt}\n\nErro de validação: {last_error}",
            PlanSchema,
            model="main",
        )
        try:
            validate_plan(plan, profile, db)
            return plan
        except (ValueError, ValidationError) as error:
            last_error = str(error)[:400]
    raise StructuredOutputError("O plano não passou nas validações.")


def current_plan(db: Session, student_id) -> Plan | None:
    return db.scalar(
        select(Plan).where(Plan.student_id == student_id).order_by(desc(Plan.version)).limit(1)
    )
