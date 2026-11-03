"""UAT data set — invented, re-runnable on a fresh database (decided 2026-11-02: no real
data from the source documents).

    python -m app.seed_uat            (from backend/, after `alembic upgrade head`)

Builds on the dev seed (`app.seed`: one user per role, four funds, employers,
categories, fees, regulatory defaults, nine members) and adds what user acceptance
testing needs, all dated relative to today so it works whenever it is loaded:

- a second principal officer (po2@…, Nkhata Bay Logistics); po@… acts for two
  employers in two funds;
- more members, a salary for every member, and beneficiary nominations;
- contribution history through the real services (payment notice → staff confirm →
  checker approves → receipt; portal schedule → allocation → checker approves), so the
  ledger, arrears and statements all agree:
    * CTE01 Chikwawa Tea — paid and credited every month up to last month;
    * LSC01 Lakeshore Sugar — paid up to two months ago; last month not sent yet;
    * NBL01 Nkhata Bay — paid up to three months ago, then in arrears, with one payment
      notice waiting for staff to confirm.

Notifications and emails produced while loading are removed at the end so testers start
with clean inboxes. Running it again adds nothing that is already there.
Logins: UAT.md (password: SEED_PASSWORD, default Pensionz2026)."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, select

from app import seed
from app.core.database import SessionLocal
from app.models.contribution import ContributionReceipt, ContributionSchedule, PaymentMethod, ReceiptStatus, ScheduleSource, ScheduleStatus
from app.models.fund import BankAccountPurpose, Fund, FundBankAccount
from app.models.identity import UserRole
from app.models.member import BeneficiaryNomination, Member, MemberSalary, MemberStatus
from app.models.mixins import utcnow
from app.models.notification import NotificationOutbox, UserNotification
from app.models.scheme import Scheme, SchemeOfficer
from app.schemas.member import BeneficiaryIn, NominationIn
from app.services import allocations, approvals, identity, member_records, periods, receipts, schedules
from app.services.receipts import ConfirmValues

EXTRA_USERS = [("po2@pensionz.dev", "Vitumbiko Principal-Officer", [UserRole.principal_officer])]
EXTRA_OFFICERS = [("NBL01", "po2@pensionz.dev")]

# More invented members: (employer, category, first, last, gender, born, joined, employee no., status)
EXTRA_MEMBERS = [
    ("CTE01", "STF", "Madalitso", "Chikoti", "male", date(1992, 2, 18), date(2024, 1, 1), "CT0131", "active"),
    ("CTE01", "STF", "Tadala", "Ngwira", "female", date(1997, 6, 9), date(2025, 1, 1), "CT0150", "active"),
    ("CTE01", "MGT", "Lusungu", "Mhango", "male", date(1981, 10, 27), date(2024, 1, 1), "CT0009", "active"),
    ("NBL01", "ALL", "Fatsani", "Kachale", "female", date(1990, 1, 3), date(2024, 2, 1), "NB2240", "active"),
    ("NBL01", "ALL", "Wongani", "Msiska", "male", date(1985, 12, 12), date(2024, 2, 1), "NB2251", "active"),
    ("LSC01", "STF", "Chikondi", "Zulu", "female", date(1993, 4, 25), date(2024, 1, 1), "LS044", "active"),
    ("LSC01", "STF", "Mphatso", "Kamanga", "male", date(1988, 8, 8), date(2025, 7, 1), "LS052", "active"),
]

# Monthly basic salary by employee number (MWK).
SALARIES = {
    "CT0001": 900000, "CT0102": 420000, "CT0117": 350000, "CT0043": 380000, "CT0131": 520000, "CT0150": 310000, "CT0009": 750000,
    "NB2201": 610000, "NB2378": 280000, "NB2240": 450000, "NB2251": 395000,
    "LS015": 480000, "LS031": 300000, "LS044": 365000, "LS052": 295000, "TCH0007": 640000,
}

# (employee no., [(name, relationship, born, share %)]) — minors get a guardian.
NOMINATIONS = [
    ("CT0001", [("John Mwale", "SPOUSE", date(1975, 5, 2), "60"), ("Tamara Mwale", "CHILD", date(2012, 9, 14), "40")]),
    ("CT0102", [("Mary Phiri", "SPOUSE", date(1993, 3, 1), "100")]),
    ("NB2201", [("Kumbukani Chirwa", "CHILD", date(2008, 1, 20), "50"), ("Luka Chirwa", "CHILD", date(2015, 6, 30), "50")]),
    ("LS015", [("Daniel Kumwenda", "SPOUSE", date(1970, 11, 11), "100")]),
]

# Employer → (principal officer, months before the current one that are left unpaid, and whether the
# last unpaid month has a payment notice waiting for confirmation)
HISTORY = {"CTE01": ("po@pensionz.dev", 0, False), "LSC01": ("po@pensionz.dev", 1, False), "NBL01": ("po2@pensionz.dev", 2, True)}


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def seed_people(db) -> None:
    seed.USERS[:] = seed.USERS + [u for u in EXTRA_USERS if u[0] not in {x[0] for x in seed.USERS}]
    seed.MEMBERS[:] = seed.MEMBERS + [m for m in EXTRA_MEMBERS if m[7] not in {x[7] for x in seed.MEMBERS}]


def seed_officers(db) -> None:
    for code, email in EXTRA_OFFICERS:
        scheme = db.execute(select(Scheme).where(Scheme.code == code)).scalar_one()
        user = identity.find_by_email(db, email)
        if not db.execute(select(SchemeOfficer.id).where(SchemeOfficer.scheme_id == scheme.id, SchemeOfficer.user_id == user.id)).first():
            db.add(SchemeOfficer(scheme_id=scheme.id, user_id=user.id))


def seed_salaries(db) -> None:
    for emp_no, amount in SALARIES.items():
        member = db.execute(select(Member).where(Member.employee_no == emp_no)).scalar_one_or_none()
        if member is None or db.execute(select(MemberSalary.id).where(MemberSalary.member_id == member.id)).first():
            continue
        value = Decimal(amount)
        db.add(MemberSalary(member_id=member.id, effective_from=member.date_joined_employer or member.date_joined_fund, basic_salary=value,
                            pensionable_salary=value, note="UAT data"))


def seed_nominations(db, maker, checker) -> None:
    for emp_no, people in NOMINATIONS:
        member = db.execute(select(Member).where(Member.employee_no == emp_no)).scalar_one_or_none()
        if member is None or db.execute(select(BeneficiaryNomination.id).where(BeneficiaryNomination.member_id == member.id)).first():
            continue
        beneficiaries = []
        for name, relationship, born, share in people:
            minor = member_records.is_minor(born)
            beneficiaries.append(BeneficiaryIn(
                full_name=name, relationship=relationship, date_of_birth=born, share_pct=Decimal(share), phone="+265 999 555 010",
                guardian_name=f"{member.first_name} {member.last_name}" if minor else None,
                guardian_relationship="PARENT" if minor else None, guardian_phone=member.mobile if minor else None,
            ))
        request = member_records.propose_nomination(db, maker, member, NominationIn(signed_date=member.date_joined_fund, beneficiaries=beneficiaries))
        approvals.approve(db, request.id, checker)


def _collections_account(db, fund: Fund) -> FundBankAccount:
    return db.execute(select(FundBankAccount).where(FundBankAccount.fund_id == fund.id,
                                                    FundBankAccount.purpose == BankAccountPurpose.collections)).scalars().first()


def _pay_month(db, scheme: Scheme, fund: Fund, month: date, officer, staff, checker, today: date, left: dict) -> None:
    """One month the way it happens in production: portal schedule, payment notice, staff confirm, allocate."""
    if db.execute(select(ContributionSchedule.id).where(ContributionSchedule.scheme_id == scheme.id, ContributionSchedule.contribution_month == month,
                                                        ContributionSchedule.status != ScheduleStatus.cancelled)).first():
        return
    schedule = schedules.create(db, officer, fund, scheme.id, month, supplementary=False, source=ScheduleSource.portal, prefill=True)
    # Members who have since left contributed up to the month they left.
    for line in [l for l in schedule.lines if l.member_id in left and month > periods.month_start(left[l.member_id][1])]:
        schedule = schedules.remove_line(db, schedule, line.id)
    if not schedule.lines:
        schedules.cancel(db, officer, schedule)
        return
    schedule = schedules.submit(db, officer, schedule)
    needed = allocations.plan_for(db, schedule).needed
    paid_on = min(periods.next_month(month) + timedelta(days=min(scheme.contribution_day, 28) - 3), today - timedelta(days=1))
    notice = receipts.submit_notice(db, officer, scheme, amount=needed, payment_date=paid_on, payment_method=PaymentMethod.eft,
                                    payer_reference=f"{scheme.code}-{month:%Y%m}", contribution_month=month, notes=None)
    account = _collections_account(db, fund)
    request = receipts.propose_confirmation(db, staff, notice, ConfirmValues(
        amount=needed, value_date=min(paid_on + timedelta(days=1), today), bank_account_id=account.id, bank_reference=f"FT{month:%y%m}{scheme.code}",
        scheme_id=scheme.id, contribution_month=month, notes=None))
    approvals.approve(db, request.id, checker)
    db.refresh(schedule)
    approvals.approve(db, allocations.propose(db, staff, schedule, None).id, checker)


def seed_history(db, today: date) -> None:
    staff = identity.find_by_email(db, "contributions@pensionz.dev")
    checker = identity.find_by_email(db, "contributions.checker@pensionz.dev")
    current = periods.month_start(today)
    # Load the past as it happened: members who have since left were active then.
    leavers = list(db.execute(select(Member).where(Member.status != MemberStatus.active)).scalars())
    left = {m.id: (m.status, m.status_effective, m.exit_date) for m in leavers}
    for m in leavers:
        m.status, m.exit_date = MemberStatus.active, None
    db.commit()
    for code, (officer_email, unpaid, notice_waiting) in HISTORY.items():
        scheme = db.execute(select(Scheme).where(Scheme.code == code)).scalar_one()
        fund = db.get(Fund, scheme.fund_id)
        officer = identity.find_by_email(db, officer_email)
        first = min(m.date_joined_fund for m in db.execute(select(Member).where(Member.scheme_id == scheme.id)).scalars())
        month = max(periods.month_start(first), periods.month_start(scheme.join_date or first))
        last_paid = _add_months(current, -1 - unpaid)
        while month <= last_paid:
            _pay_month(db, scheme, fund, month, officer, staff, checker, today, left)
            month = _add_months(month, 1)
        if notice_waiting and unpaid:
            waiting_month = _add_months(last_paid, 1)
            exists = db.execute(select(ContributionReceipt.id).where(ContributionReceipt.scheme_id == scheme.id,
                                                                     ContributionReceipt.contribution_month == waiting_month)).first()
            if not exists:
                receipts.submit_notice(db, officer, scheme, amount=Decimal("190000.00"), payment_date=min(today, _add_months(waiting_month, 1) + timedelta(days=12)),
                                       payment_method=PaymentMethod.rtgs, payer_reference=f"{scheme.code}-{waiting_month:%Y%m} part",
                                       contribution_month=waiting_month, notes="Part payment — balance to follow")
    for m in leavers:
        m.status, m.status_effective, m.exit_date = left[m.id]
    db.commit()


def clear_inboxes(db, since) -> int:
    """Notifications created while loading the data are noise for testers."""
    n = db.execute(delete(UserNotification).where(UserNotification.created_at >= since)).rowcount
    db.execute(delete(NotificationOutbox).where(NotificationOutbox.created_at >= since))
    return n


def main() -> None:
    started = utcnow()
    today = receipts.today()
    with SessionLocal() as db:
        seed_people(db)
        users = seed.seed_users(db)
        funds = seed.seed_funds(db)
        seed.grant_seed_access(db)
        seed.seed_periods(db)
        seed.seed_schemes(db)
        seed.seed_regulatory(db)
        seed.seed_options(db)
        seed.seed_categories(db)
        seed.seed_fees(db)
        seed.seed_members(db)
        seed_officers(db)
        seed_salaries(db)
        db.commit()
        seed_nominations(db, identity.find_by_email(db, "members@pensionz.dev"), identity.find_by_email(db, "members.checker@pensionz.dev"))
        seed_history(db, today)
        cleared = clear_inboxes(db, started)
        db.commit()
        members = db.execute(select(Member.id)).all()
        confirmed = db.execute(select(ContributionReceipt.id).where(ContributionReceipt.status == ReceiptStatus.confirmed)).all()
    print(f"UAT seed complete: {users} user(s), {funds} fund(s) created; {len(members)} members, {len(confirmed)} confirmed receipts; "
          f"{cleared} loading notification(s) cleared. Password for all: {seed.DEV_PASSWORD}.")


if __name__ == "__main__":
    main()
