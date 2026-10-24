from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.clock import Clock
from app.core.dependencies import get_clock
from app.db.session import get_db
from app.models import Consent, StudentProfile, User
from app.schemas.ai import ConsentSubmission
from app.security.auth import require_csrf, require_role

router = APIRouter(prefix="/api/me", tags=["consents"])

CONSENT_TEXTS = {
    "memory": {
        "version": "v1",
        "text": "A Permaneço pode guardar fatos úteis que você contar para retomar em conversas futuras. É opcional, você pode consultar ou apagar suas memórias quando quiser.",
    },
    "voice": {
        "version": "v1",
        "text": "Se você usar voz, o áudio será transcrito para permitir a conversa. Esse recurso é opcional.",
    },
    "risk_protocol": {
        "version": "v1",
        "text": "Entendi que, se houver risco à vida, a equipe de apoio poderá ser avisada para oferecer ajuda. A Permaneço não substitui atendimento profissional ou de emergência.",
    },
}


@router.get("/consents")
def get_consents(
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
) -> dict:
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    accepted = {}
    for consent_type in CONSENT_TEXTS:
        row = db.scalar(
            select(Consent)
            .where(Consent.user_id == user.id, Consent.consent_type == consent_type)
            .order_by(Consent.created_at.desc())
            .limit(1)
        )
        accepted[consent_type] = bool(row and row.accepted)
    is_minor = profile is not None and profile.age_years is not None and profile.age_years < 18
    return {
        "texts": CONSENT_TEXTS,
        "accepted": accepted,
        "age_confirmed": not is_minor and bool(profile and profile.age_years is not None),
        "chat_allowed": not is_minor and accepted["risk_protocol"],
        "minor_message": (
            "Para receber apoio, procure a instituição. O chat não está disponível para menores de 18 anos."
            if is_minor
            else None
        ),
    }


@router.post("/consents", dependencies=[Depends(require_csrf)])
def update_consents(
    payload: ConsentSubmission,
    user: User = Depends(require_role("student")),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> dict:
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil não encontrado.")
    if (profile.age_years is not None and profile.age_years < 18) or not payload.age_confirmed:
        raise HTTPException(
            status_code=403,
            detail="Para receber apoio, procure a instituição. O chat não está disponível para menores de 18 anos.",
        )
    if not payload.risk_protocol_accepted:
        raise HTTPException(
            status_code=400, detail="É necessário aceitar a ciência do protocolo de risco."
        )
    values = {
        "memory": payload.memory_accepted,
        "voice": payload.voice_accepted,
        "risk_protocol": payload.risk_protocol_accepted,
    }
    for consent_type, accepted in values.items():
        row = db.scalar(
            select(Consent)
            .where(Consent.user_id == user.id, Consent.consent_type == consent_type)
            .order_by(Consent.created_at.desc())
            .limit(1)
        )
        if row:
            row.accepted = accepted
            row.text_version = CONSENT_TEXTS[consent_type]["version"]
            row.created_at = clock.now()
        else:
            db.add(
                Consent(
                    user_id=user.id,
                    consent_type=consent_type,
                    accepted=accepted,
                    text_version=CONSENT_TEXTS[consent_type]["version"],
                    created_at=clock.now(),
                )
            )
    db.commit()
    return {"accepted": values, "chat_allowed": True}
