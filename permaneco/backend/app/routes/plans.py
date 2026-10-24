import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response, status
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.ai.background import process_plan_proposal
from app.db.session import get_db
from app.models import KnowledgeItem, Memory, NextStep, Plan, PlanProposal, User
from app.security.auth import require_csrf, require_role

router = APIRouter(prefix="/api/me", tags=["student-ai"])


@router.get("/plan")
def get_plan(
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> dict:
    plans = list(
        db.scalars(
            select(Plan).where(Plan.student_id == user.id).order_by(desc(Plan.version)).limit(2)
        )
    )
    if not plans:
        return {"current": None, "previous_version": None, "sources": []}
    current = plans[0]
    try:
        content = json.loads(current.content)
    except json.JSONDecodeError:
        content = {}
    slugs = set()
    for path in content.get("carreira", {}).get("paths", []):
        slugs.update(path.get("knowledge_ids", []))
    for aid in content.get("financas", {}).get("auxilios", []):
        slugs.add(aid.get("knowledge_id", ""))
    sources = db.scalars(
        select(KnowledgeItem).where(
            KnowledgeItem.slug.in_(slugs), KnowledgeItem.is_active.is_(True)
        )
    )
    return {
        "current": {
            "version": current.version,
            "plan": content,
            "change_summary": current.change_summary,
            "created_at": current.created_at,
        },
        "previous_version": plans[1].version if len(plans) > 1 else None,
        "sources": [
            {
                "slug": item.slug,
                "title": item.title,
                "source_url": item.source_url,
                "kind": item.kind,
            }
            for item in sources
        ],
    }


@router.get("/plan/proposals")
def get_pending_proposals(
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> list[dict]:
    proposals = db.scalars(
        select(PlanProposal)
        .where(PlanProposal.student_id == user.id, PlanProposal.status == "pending")
        .order_by(desc(PlanProposal.created_at))
    )
    return [
        {
            "id": str(proposal.id),
            "section": proposal.section,
            "change": proposal.change,
            "created_at": proposal.created_at,
        }
        for proposal in proposals
    ]


@router.post(
    "/plan/proposals/{proposal_id}/confirm",
    status_code=202,
    dependencies=[Depends(require_csrf)],
)
def confirm_proposal(
    proposal_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> dict:
    proposal = db.scalar(
        select(PlanProposal).where(
            PlanProposal.id == proposal_id,
            PlanProposal.student_id == user.id,
        )
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="Esta proposta já foi respondida.")
    proposal.status = "confirmed"
    db.commit()
    background_tasks.add_task(process_plan_proposal, str(proposal.id), str(user.id))
    return {"status": "confirmed"}


@router.post(
    "/plan/proposals/{proposal_id}/reject",
    dependencies=[Depends(require_csrf)],
)
def reject_proposal(
    proposal_id: uuid.UUID,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> dict:
    proposal = db.scalar(
        select(PlanProposal).where(
            PlanProposal.id == proposal_id,
            PlanProposal.student_id == user.id,
        )
    )
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")
    if proposal.status != "pending":
        raise HTTPException(status_code=409, detail="Esta proposta já foi respondida.")
    proposal.status = "rejected"
    db.commit()
    return {"status": "rejected"}


@router.get("/next-steps")
def get_next_steps(
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> list[dict]:
    steps = db.scalars(
        select(NextStep)
        .where(NextStep.student_id == user.id, NextStep.completed.is_(False))
        .order_by(desc(NextStep.created_at))
    )
    return [{"text": step.content, "due_text": step.due_text} for step in steps]


@router.get("/memories")
def get_memories(
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> list[dict]:
    memories = db.scalars(
        select(Memory)
        .where(Memory.student_id == user.id, Memory.is_active.is_(True))
        .order_by(desc(Memory.updated_at))
    )
    return [
        {
            "id": str(memory.id),
            "category": memory.category,
            "content": memory.content,
            "is_sensitive": memory.is_sensitive,
        }
        for memory in memories
    ]


@router.delete(
    "/memories/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
)
def delete_memory(
    memory_id: uuid.UUID,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> Response:
    memory = db.scalar(
        select(Memory).where(
            Memory.id == memory_id,
            Memory.student_id == user.id,
        )
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="Memória não encontrada.")
    memory.is_active = False
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
