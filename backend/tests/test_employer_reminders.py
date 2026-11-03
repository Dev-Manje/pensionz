"""Employer notifications (FR-NOT-003, FR-CON-008): the daily employer_reminders job
(schedule due, arrears with escalation) and schedule notices to principal officers.
EMP01 pays by the 14th of the following month; members from July 2026."""
from datetime import date

import pytest

from app.jobs import employer_reminders
from app.models.contribution import ContributionSchedule, ScheduleSource, ScheduleStatus
from app.models.identity import UserRole
from app.models.notification import UserNotification
from app.models.scheme import SchemeOfficer
from app.services import fund_access
from tests.factories import auth_headers, make_user
from tests.test_arrears import staff, world  # noqa: F401 — fixtures
from tests.test_portal_remittances import code_for, start


@pytest.fixture
def officer(db, world):
    user = make_user(db, UserRole.principal_officer)
    db.add(SchemeOfficer(scheme_id=world[1].id, user_id=user.id))
    db.flush()
    db.refresh(world[1])
    return user


@pytest.fixture
def contributions(db, world):
    user = make_user(db, UserRole.contributions_officer)
    fund_access.grant(db, user.id, world[0].id, None)
    db.flush()
    return user


def events(db, user, event):
    return db.query(UserNotification).filter_by(user_id=user.id, event=event).all()


def test_schedule_due_reminders_a_week_before_and_on_the_day(db, world, officer):
    employer_reminders.run(db, date(2026, 11, 7))  # October due 14 Nov: 7 days
    [note] = events(db, officer, "employer.schedule_due")
    assert "Oct 2026" in note.title and "send the schedule and pay" in note.body and "in 7 days" in note.body
    employer_reminders.run(db, date(2026, 11, 8))
    assert len(events(db, officer, "employer.schedule_due")) == 1
    employer_reminders.run(db, date(2026, 11, 14))
    assert "today" in events(db, officer, "employer.schedule_due")[-1].title


def test_no_due_reminder_once_the_schedule_is_sent(db, world, officer):
    fund, scheme, _ = world
    db.add(ContributionSchedule(fund_id=fund.id, scheme_id=scheme.id, contribution_month=date(2026, 10, 1), reference="S10",
                                status=ScheduleStatus.ready, source=ScheduleSource.portal))
    db.flush()
    employer_reminders.run(db, date(2026, 11, 7))
    assert events(db, officer, "employer.schedule_due") == []


def test_arrears_reminder_and_escalation(db, world, officer, contributions):
    employer_reminders.run(db, date(2026, 8, 15))  # July 1 day overdue
    [note] = events(db, officer, "employer.arrears")
    assert "MWK 45,000.00" in note.title and "Jul 2026" in note.body
    assert events(db, contributions, "employer.arrears_escalated") == []
    employer_reminders.run(db, date(2026, 8, 16))  # 2 days: no reminder
    assert len(events(db, officer, "employer.arrears")) == 1
    employer_reminders.run(db, date(2026, 10, 13))  # July 60 days overdue → escalate
    assert "MWK 90,000.00" in events(db, officer, "employer.arrears")[-1].title  # July + August
    [escalation] = events(db, contributions, "employer.arrears_escalated")
    assert "Jul 2026" in escalation.body


def test_schedule_notices_to_officers(client, db, world, officer, contributions):
    colleague = make_user(db, UserRole.principal_officer)
    db.add(SchemeOfficer(scheme_id=world[1].id, user_id=colleague.id))
    db.flush()
    s = start(client, officer, world[1]).json()
    sent = client.post(f"/api/v1/po/schedules/{s['id']}/submit", headers=auth_headers(officer), json={"code": code_for(client, db, officer)})
    assert sent.status_code == 200, sent.text
    assert len(events(db, officer, "schedule.received")) == 1 and len(events(db, colleague, "schedule.received")) == 1
    # Staff send it back for correction: the officers are told and can edit it again.
    reopened = client.post(f"/api/v1/schedules/{s['id']}/reopen", headers=auth_headers(contributions))
    assert reopened.status_code == 200, reopened.text
    [note] = events(db, officer, "schedule.reopened")
    assert note.link == f"/po/schedules/{s['id']}"
    assert client.get(f"/api/v1/po/schedules/{s['id']}", headers=auth_headers(officer)).json()["can_edit"] is True
