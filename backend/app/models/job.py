import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import UUIDPKMixin, str_enum, utcnow


class JobRunStatus(str, enum.Enum):
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class JobRun(UUIDPKMixin, Base):
    """One row per (scheduled job, business date) — the idempotency key for
    background work: a job runs for a date only if it has no succeeded row."""

    __tablename__ = "job_run"
    __table_args__ = (UniqueConstraint("job_name", "as_of_date", name="uq_job_run_job_date"),)

    job_name: Mapped[str] = mapped_column(String(100), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[JobRunStatus] = mapped_column(str_enum(JobRunStatus, 20), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
