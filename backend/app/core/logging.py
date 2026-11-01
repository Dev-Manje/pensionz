import logging

from app.core.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging() -> None:
    """Configure the root logger once per process (API and worker both call
    this). Without it the root level stays at WARNING and every app .info()
    is silently dropped. Uvicorn's own loggers keep their handlers and don't
    propagate, so this doesn't duplicate request lines."""
    logging.basicConfig(level=settings.log_level.upper(), format=LOG_FORMAT, force=True)
    # SQLAlchemy echoes every statement at INFO — keep it quiet unless asked.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
