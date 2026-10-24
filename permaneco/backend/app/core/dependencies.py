from app.core.clock import Clock, DemoClock, SystemClock
from app.core.config import settings
from app.db.session import SessionLocal


def get_clock() -> Clock:
    if settings.demo_mode:
        return DemoClock(SessionLocal, enabled=True)
    return SystemClock()
