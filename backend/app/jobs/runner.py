import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.jobs import Job
from app.models.job import JobRun, JobRunStatus
from app.models.mixins import utcnow

logger = logging.getLogger("app.jobs")

# A `running` row older than this is assumed to belong to a worker that died
# mid-run, and may be claimed again.
STALE_RUN_AFTER = timedelta(hours=1)


def _claim(db: Session, job: Job, as_of: date) -> JobRun | None:
    """Atomically take ownership of (job, as_of). Returns the claimed row, or
    None if the date already succeeded or another worker is running it."""
    inserted = db.execute(
        insert(JobRun)
        .values(job_name=job.name, as_of_date=as_of, status=JobRunStatus.running, attempts=1, started_at=utcnow())
        .on_conflict_do_nothing(constraint="uq_job_run_job_date")
        .returning(JobRun.id)
    ).scalar_one_or_none()
    if inserted is not None:
        db.commit()
        return db.get(JobRun, inserted)

    existing = db.execute(
        select(JobRun).where(JobRun.job_name == job.name, JobRun.as_of_date == as_of).with_for_update(skip_locked=True)
    ).scalar_one_or_none()
    if existing is None or existing.status == JobRunStatus.succeeded:
        db.rollback()
        return None
    if existing.status == JobRunStatus.running and utcnow() - existing.started_at < STALE_RUN_AFTER:
        db.rollback()
        return None
    existing.status = JobRunStatus.running
    existing.attempts += 1
    existing.started_at = utcnow()
    existing.finished_at = None
    existing.summary = None
    db.commit()
    return existing


def run_job(db: Session, job: Job, as_of: date) -> JobRunStatus | None:
    """Run `job` for business date `as_of` at most once successfully.
    Returns the resulting status, or None if it was skipped (already done or
    in progress elsewhere)."""
    run = _claim(db, job, as_of)
    if run is None:
        logger.info("job %s for %s skipped (already done or running)", job.name, as_of)
        return None

    logger.info("job %s for %s started (attempt %d)", job.name, as_of, run.attempts)
    try:
        summary = job.run(db, as_of)
    except Exception as exc:
        db.rollback()
        logger.exception("job %s for %s failed", job.name, as_of)
        run = db.get(JobRun, run.id)
        run.status = JobRunStatus.failed
        run.summary = f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = utcnow()
        db.commit()
        return JobRunStatus.failed

    run = db.get(JobRun, run.id)
    run.status = JobRunStatus.succeeded
    run.summary = summary
    run.finished_at = utcnow()
    db.commit()
    logger.info("job %s for %s succeeded: %s", job.name, as_of, summary)
    return JobRunStatus.succeeded


def due_dates(db: Session, job: Job, now: datetime) -> list[date]:
    """Business dates `job` still owes, oldest first, as of local time `now`.
    Covers today (once past run_at) plus up to settings.job_catchup_days of
    missed or failed days — but never days before the job's first ever run,
    so a newly added job doesn't backfill history it was never meant to see."""
    today = now.date()
    last = today if now.time() >= job.run_at else today - timedelta(days=1)
    first_ever = db.execute(select(func.min(JobRun.as_of_date)).where(JobRun.job_name == job.name)).scalar()
    start = max(today - timedelta(days=settings.job_catchup_days - 1), first_ever or today)
    if not job.catch_up:
        start = max(start, last)
    if start > last:
        return []
    done = set(
        db.execute(
            select(JobRun.as_of_date).where(
                JobRun.job_name == job.name,
                JobRun.status == JobRunStatus.succeeded,
                JobRun.as_of_date.between(start, last),
            )
        ).scalars()
    )
    return [d for d in (start + timedelta(days=i) for i in range((last - start).days + 1)) if d not in done]
