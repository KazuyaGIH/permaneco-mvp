from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    def __init__(self, instant: datetime):
        self.instant = instant

    def now(self) -> datetime:
        return self.instant


class DemoClock:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        base_clock: Clock | None = None,
        enabled: bool | None = None,
    ):
        self.session_factory = session_factory
        self.base_clock = base_clock or SystemClock()
        self.enabled = settings.demo_mode if enabled is None else enabled

    def now(self) -> datetime:
        instant = self.base_clock.now()
        if not self.enabled:
            return instant
        from app.models import DemoClockSetting

        with self.session_factory() as session:
            setting = session.scalar(select(DemoClockSetting).limit(1))
            offset = setting.offset_seconds if setting else 0
        return instant + timedelta(seconds=offset)
