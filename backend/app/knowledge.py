from datetime import date
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KnowledgeItem


def load_knowledge(db: Session) -> None:
    items_path = Path(__file__).resolve().parents[2] / "knowledge" / "items.yaml"
    for item in yaml.safe_load(items_path.read_text(encoding="utf-8")):
        verified_at = date.fromisoformat(item["verificado_em"]) if item["verificado_em"] else None
        record = db.scalar(select(KnowledgeItem).where(KnowledgeItem.slug == item["id"]))
        values = {
            "kind": item["tipo"],
            "title": item["titulo"],
            "content": item["conteudo"],
            "source_url": item["fonte_url"],
            "verified_at": verified_at,
            "is_active": item["ativo"],
        }
        if record is None:
            db.add(KnowledgeItem(slug=item["id"], **values))
        else:
            for key, value in values.items():
                setattr(record, key, value)
