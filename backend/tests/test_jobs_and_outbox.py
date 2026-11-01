from datetime import date

from app.jobs import JOBS
from app.jobs.runner import run_job
from app.models.identity import UserRole
from app.models.job import JobRunStatus
from app.models.notification import OutboxStatus
from app.services import notifications
from app.services.notification_delivery import deliver_due, render_email
from tests.factories import make_user


def test_job_runs_once_per_date(db):
    db.commit()  # the runner commits/rolls back; keep fixtures out of its rollback
    job = JOBS["purge_expired_links"]
    assert run_job(db, job, date(2026, 1, 5)) == JobRunStatus.succeeded
    assert run_job(db, job, date(2026, 1, 5)) is None


def test_outbox_without_smtp_is_marked_skipped(db):
    user = make_user(db, UserRole.member)
    notifications.notify_password_changed(db, user, "changed")
    db.commit()
    assert deliver_due(db) >= 1
    from app.models.notification import NotificationOutbox

    row = db.query(NotificationOutbox).filter_by(recipient_user_id=user.id).one()
    assert row.status == OutboxStatus.skipped


def test_email_render_has_link_and_escapes_html():
    text, page = render_email("Hello <b>", "Line one\nLine two", "/approvals/1")
    assert "http://localhost:5178/approvals/1" in text
    assert "&lt;b&gt;" in page
