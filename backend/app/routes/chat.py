import json
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.background import process_conversation_end
from app.ai.pipeline import stream_message
from app.ai.providers.factory import get_provider
from app.core.clock import Clock
from app.core.dependencies import get_clock
from app.db.session import get_db
from app.models import Consent, Conversation, Message, StudentProfile, User
from app.schemas.ai import ConversationCreate, MessageCreate
from app.security.auth import require_csrf, require_role

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _chat_allowed(db: Session, user: User, profile: StudentProfile) -> bool:
    if profile.age_years is not None and profile.age_years < 18:
        return False
    return bool(
        db.scalar(
            select(Consent.id)
            .where(
                Consent.user_id == user.id,
                Consent.consent_type == "risk_protocol",
                Consent.accepted.is_(True),
            )
            .limit(1)
        )
    )


def _get_owned_conversation(db: Session, user: User, conversation_id: uuid.UUID):
    conversation = db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.student_id == user.id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return conversation


@router.post("/conversations", dependencies=[Depends(require_csrf)])
def create_conversation(
    payload: ConversationCreate,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> dict:
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    if not _chat_allowed(db, user, profile):
        raise HTTPException(
            status_code=403,
            detail="Conclua o cadastro de consentimento antes de iniciar uma conversa.",
        )
    conversation = Conversation(
        student_id=user.id,
        kind=payload.kind,
        channel=profile.preferred_channel or "texto",
    )
    db.add(conversation)
    db.commit()
    return {"id": str(conversation.id), "kind": conversation.kind, "channel": conversation.channel}


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: uuid.UUID,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> dict:
    conversation = _get_owned_conversation(db, user, conversation_id)
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    )
    return {
        "kind": conversation.kind,
        "channel": conversation.channel,
        "ended_at": conversation.ended_at,
        "messages": [
            {"role": message.role, "content": message.content, "created_at": message.created_at}
            for message in messages
        ],
    }


@router.post(
    "/conversations/{conversation_id}/messages",
    dependencies=[Depends(require_csrf)],
)
def send_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> StreamingResponse:
    conversation = _get_owned_conversation(db, user, conversation_id)
    if conversation.ended_at:
        raise HTTPException(status_code=409, detail="Esta conversa já foi encerrada.")
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if not profile:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    if not _chat_allowed(db, user, profile):
        raise HTTPException(
            status_code=403,
            detail="Conclua o cadastro de consentimento antes de conversar.",
        )

    def events() -> Iterator[str]:
        for item in stream_message(
            db,
            conversation,
            profile,
            payload.text,
            lambda: get_provider(),
            clock,
        ):
            event_name = item["event"]
            if event_name == "delta":
                data = {"text": item["data"], "replace": item.get("replace", False)}
            elif event_name == "tool":
                data = {"name": item["name"]}
            elif event_name == "done":
                data = item["data"]
            else:
                data = {"message": item["data"]}
            yield f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/conversations/{conversation_id}/end",
    status_code=202,
    dependencies=[Depends(require_csrf)],
)
def end_conversation(
    conversation_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict:
    conversation = _get_owned_conversation(db, user, conversation_id)
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if not profile or not _chat_allowed(db, user, profile):
        raise HTTPException(status_code=403, detail="Consentimento obrigatório não registrado.")
    if not conversation.ended_at:
        conversation.ended_at = clock.now()
        db.commit()
        background_tasks.add_task(process_conversation_end, str(conversation.id), str(user.id))
    return {"status": "processing"}
