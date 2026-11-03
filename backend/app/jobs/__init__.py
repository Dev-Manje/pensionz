"""Scheduled background jobs. Each job is a plain function
`run(db, as_of: date) -> str` that commits its own work and returns a short
summary. Jobs must be idempotent: the runner guarantees one successful run per
(job, business date) via the job_run table, but a job may be retried after a
crash part-way through.

To add a job: write app/jobs/<name>.py and register it in JOBS below
(planned jobs are listed in the pz-backend-architecture skill)."""
from dataclasses import dataclass
from datetime import date, time
from typing import Callable

from sqlalchemy.orm import Session

from app.jobs import employer_reminders, kyc_expiry_reminders, purge_expired_links


@dataclass(frozen=True)
class Job:
    name: str
    run: Callable[[Session, date], str]
    # Earliest local business time (settings.business_timezone) the job may run for a date.
    run_at: time
    # Replay missed days after downtime; reminder-style jobs only need the latest day.
    catch_up: bool = True


JOBS: dict[str, Job] = {
    job.name: job
    for job in [
        Job("purge_expired_links", purge_expired_links.run, time(1, 0), catch_up=False),
        Job("kyc_expiry_reminders", kyc_expiry_reminders.run, time(7, 0), catch_up=False),
        Job("employer_reminders", employer_reminders.run, time(7, 30), catch_up=False),
    ]
}
