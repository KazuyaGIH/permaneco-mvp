from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings

_WEEKDAYS_PT_BR = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def to_app_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(settings.app_timezone))


def format_app_datetime(value: datetime) -> str:
    localized = to_app_timezone(value)
    return (
        f"{_WEEKDAYS_PT_BR[localized.weekday()]}, "
        f"{localized:%Y-%m-%d %H:%M} ({settings.app_timezone})"
    )
