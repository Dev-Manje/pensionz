"""Background worker: delivers queued notifications (notification_outbox)
every few seconds and runs scheduled jobs (app/jobs) on a polling loop.

    python -m app.worker                          # run forever (docker compose `worker`)
    python -m app.worker list                     # show jobs and recent runs
    python -m app.worker run <job> [--as-of DATE] # run one job now (backfill/manual)

Safe to run more than one copy: the job_run table makes each (job, date)
succeed at most once, and outbox rows are claimed with SKIP LOCKED."""
import argparse
import logging
import signal
import threading
import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging
from app.jobs import JOBS
from app.jobs.runner import due_dates, run_job
from app.models.job import JobRun
from app.services.notification_delivery import deliver_due

logger = logging.getLogger("app.worker")


def business_now() -> datetime:
    return datetime.now(ZoneInfo(settings.business_timezone))


def tick() -> None:
    """One pass: run every job for every business date it still owes."""
    now = business_now()
    for job in JOBS.values():
        with SessionLocal() as db:
            for as_of in due_dates(db, job, now):
                run_job(db, job, as_of)


def deliver_notifications() -> None:
    with SessionLocal() as db:
        deliver_due(db)


def serve() -> None:
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    logger.info(
        "worker started: %d job(s) %s, polling every %ds; outbox every %ds",
        len(JOBS), sorted(JOBS), settings.worker_poll_seconds, settings.outbox_poll_seconds,
    )
    next_tick = time.monotonic()
    while not stop.is_set():
        # Each step is guarded separately: a broken pass (e.g. DB briefly
        # down) must not kill the worker or starve the other step.
        try:
            deliver_notifications()
        except Exception:
            logger.exception("notification delivery failed")
        if time.monotonic() >= next_tick:
            try:
                tick()
            except Exception:
                logger.exception("worker tick failed")
            next_tick = time.monotonic() + settings.worker_poll_seconds
        stop.wait(settings.outbox_poll_seconds)
    logger.info("worker stopped")


def list_jobs() -> None:
    with SessionLocal() as db:
        for job in JOBS.values():
            runs = db.query(JobRun).filter(JobRun.job_name == job.name).order_by(JobRun.as_of_date.desc()).limit(5).all()
            print(f"{job.name} (daily after {job.run_at:%H:%M} {settings.business_timezone})")
            for r in runs:
                print(f"  {r.as_of_date}  {r.status.value:<9}  attempts={r.attempts}  {r.summary or ''}")
            if not runs:
                print("  (never run)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.worker")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("list")
    run_parser = sub.add_parser("run")
    run_parser.add_argument("job", choices=sorted(JOBS))
    run_parser.add_argument("--as-of", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    setup_logging()
    if args.command == "list":
        list_jobs()
    elif args.command == "run":
        with SessionLocal() as db:
            status = run_job(db, JOBS[args.job], args.as_of or business_now().date())
        print(status.value if status else "skipped (already succeeded or running)")
    else:
        serve()


if __name__ == "__main__":
    main()
