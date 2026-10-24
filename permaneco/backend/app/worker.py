import logging
from threading import Event

from apscheduler.schedulers.background import BackgroundScheduler

from app.core.dependencies import get_clock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("app.worker")


def main() -> None:
    clock = get_clock()

    def heartbeat() -> None:
        logger.info("Worker heartbeat at %s", clock.now().isoformat())

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(heartbeat, "interval", seconds=60)
    heartbeat()
    scheduler.start()
    try:
        Event().wait()
    except KeyboardInterrupt:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
