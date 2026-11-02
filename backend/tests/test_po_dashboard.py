"""Principal officer dashboard (FR-PRT-001): this month's remittance per
employer, arrears totals and recent activity — as at 2 Nov 2026, when October's
contributions are due by 14 Nov."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.contribution import (
    AllocationStatus, ContributionAllocation, ContributionReceipt, ContributionSchedule, PaymentMethod, ReceiptSource,
    ReceiptStatus, ScheduleSource, ScheduleStatus,
)
from app.models.identity import UserRole
from app.models.scheme import Scheme, SchemeOfficer
from app.services import portal
from tests.factories import auth_headers, make_fund, make_user
from tests.test_arrears import AS_AT, paid, staff, world  # noqa: F401 — fixtures

D = Decimal
OCT = date(2026, 10, 1)


@pytest.fixture
def officer(db, world):
    _, scheme, _ = world
    user = make_user(db, UserRole.principal_officer)
    db.add(SchemeOfficer(scheme_id=scheme.id, user_id=user.id))
    db.flush()
    return user


def schedule(db, fund, scheme, month, status, total="45000", submitted=None):
    s = ContributionSchedule(fund_id=fund.id, scheme_id=scheme.id, contribution_month=month, reference=f"S{month:%m}",
                             status=status, source=ScheduleSource.portal, total=D(total), line_count=2, submitted_at=submitted)
    db.add(s)
    db.flush()
    return s


def notice(db, fund, scheme, month, amount, status=ReceiptStatus.notified, number="N000001"):
    r = ContributionReceipt(fund_id=fund.id, scheme_id=scheme.id, status=status, source=ReceiptSource.portal_notice,
                            notice_number=f"{fund.code}-{number}", payment_method=PaymentMethod.eft, notified_amount=D(amount),
                            amount=D(amount) if status == ReceiptStatus.confirmed else None, payment_date=date(2026, 11, 1),
                            contribution_month=month)
    db.add(r)
    db.flush()
    return r


def test_remittance_month_is_last_month():
    assert portal.remittance_month(date(2026, 11, 2)) == OCT
    assert portal.remittance_month(date(2026, 1, 31)) == date(2025, 12, 1)


def test_nothing_sent_yet(db, world):
    _, scheme, _ = world
    current = portal.current_remittance(db, scheme, AS_AT)
    assert (current["month"], current["due_date"], current["days_to_due"], current["stage"]) == (OCT, date(2026, 11, 14), 12, "not_started")
    assert current["schedule_reference"] is None and current["notified_amount"] == D("0")


def test_overdue_shows_negative_days(db, world):
    _, scheme, _ = world
    assert portal.current_remittance(db, scheme, date(2026, 11, 20))["days_to_due"] == -6


def test_payment_without_schedule(db, world):
    fund, scheme, _ = world
    notice(db, fund, scheme, OCT, "45000")
    notice(db, fund, scheme, OCT, "999", status=ReceiptStatus.rejected, number="N000002")  # ignored
    current = portal.current_remittance(db, scheme, AS_AT)
    assert (current["stage"], current["notified_amount"], current["confirmed_amount"]) == ("payment_only", D("45000"), D("0"))


@pytest.mark.parametrize("status,stage", [
    (ScheduleStatus.draft, "draft"), (ScheduleStatus.ready, "awaiting_allocation"), (ScheduleStatus.allocated, "allocated"),
])
def test_schedule_stage(db, world, status, stage):
    fund, scheme, _ = world
    s = schedule(db, fund, scheme, OCT, status)
    notice(db, fund, scheme, OCT, "45000", status=ReceiptStatus.confirmed)
    current = portal.current_remittance(db, scheme, AS_AT)
    assert (current["stage"], current["schedule_reference"], current["schedule_total"]) == (stage, s.reference, D("45000"))
    assert current["confirmed_amount"] == D("45000")


def test_cancelled_and_supplementary_schedules_do_not_count(db, world):
    fund, scheme, _ = world
    schedule(db, fund, scheme, OCT, ScheduleStatus.cancelled)
    supp = schedule(db, fund, scheme, OCT, ScheduleStatus.ready)
    supp.supplementary = True
    supp.reference = "S10-SUPP"
    db.flush()
    assert portal.current_remittance(db, scheme, AS_AT)["stage"] == "not_started"


def test_arrears_summary_counts_only_overdue_months(db, world):
    fund, scheme, people = world
    paid(db, fund, scheme, date(2026, 8, 1), [(people[0], D("10000"), D("20000")), (people[1], D("5000"), D("10000"))])
    summary = portal.arrears_summary(db, scheme, AS_AT)
    # July and September unpaid (45,000 each); August paid; October not due yet.
    assert (summary["total"], summary["overdue_months"], summary["oldest_month"]) == (D("90000.00"), 2, date(2026, 7, 1))
    assert summary["oldest_days_overdue"] == 80 and summary["interest"] is None


def test_activity_newest_first_and_limited_to_own_employers(db, world, officer):
    fund, scheme, _ = world
    now = datetime.now(timezone.utc)
    sent = schedule(db, fund, scheme, OCT, ScheduleStatus.allocated, submitted=now - timedelta(days=2))
    db.add(ContributionAllocation(fund_id=fund.id, scheme_id=scheme.id, schedule_id=sent.id, status=AllocationStatus.posted,
                                  schedule_total=D("45000"), amount=D("45000"), net_to_members=D("44100"), posted_at=now - timedelta(hours=1)))
    rejected = notice(db, fund, scheme, OCT, "45000", status=ReceiptStatus.rejected)
    rejected.rejection_reason = "No such payment on the bank statement"
    old = schedule(db, fund, scheme, date(2026, 6, 1), ScheduleStatus.allocated, submitted=now - timedelta(days=200))
    other = Scheme(fund_id=fund.id, code="OTH01", name="Someone Else Ltd", contribution_day=14)
    db.add(other)
    db.flush()
    schedule(db, fund, other, OCT, ScheduleStatus.ready, submitted=now)
    db.flush()

    activity = portal.dashboard(db, officer, AS_AT)["activity"]
    kinds = [a["kind"] for a in activity]
    assert "allocated" in kinds and "schedule_sent" in kinds and "notice_rejected" in kinds
    assert all(a["scheme_name"] == scheme.name for a in activity)  # nothing from OTH01
    assert [a["at"] for a in activity] == sorted((a["at"] for a in activity), reverse=True)
    assert not any(old.reference in a["title"] for a in activity)  # older than 90 days
    credited = next(a for a in activity if a["kind"] == "allocated")
    assert credited["title"] == "Contributions for Oct 2026 credited to members" and "MWK 44,100.00" in credited["detail"]
    assert next(a for a in activity if a["kind"] == "notice_rejected")["detail"] == "No such payment on the bank statement"


def test_dashboard_api_covers_employers_in_several_funds(client, db, world, officer, staff):
    fund, scheme, _ = world
    other_fund = make_fund(db, staff)
    second = Scheme(fund_id=other_fund.id, code="EMP02", name="Second Employer Ltd", contribution_day=10)
    db.add(second)
    db.flush()
    db.add(SchemeOfficer(scheme_id=second.id, user_id=officer.id))
    db.flush()
    response = client.get("/api/v1/po/dashboard", headers=auth_headers(officer))
    assert response.status_code == 200, response.text
    data = response.json()
    assert {(s["code"], s["fund_code"]) for s in data["schemes"]} == {("EMP01", fund.code), ("EMP02", other_fund.code)}
    first = next(s for s in data["schemes"] if s["code"] == "EMP01")
    assert first["current"]["stage"] == "not_started" and first["arrears"]["overdue_months"] >= 1


def test_dashboard_access(client, db, world, officer, staff):
    stranger = make_user(db, UserRole.principal_officer)
    assert client.get("/api/v1/po/dashboard", headers=auth_headers(stranger)).json()["schemes"] == []
    assert client.get("/api/v1/po/dashboard", headers=auth_headers(staff)).status_code == 403
    assert client.get("/api/v1/po/dashboard").status_code == 401
