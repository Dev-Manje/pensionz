"""Dev seed, safe to run repeatedly (existing rows are left alone):
- one user per role, plus a second admin so user-access changes can be approved;
- four invented funds (umbrella DC, stand-alone DC, DB, personal pension) with
  trustees, a bank account, employers and an open processing month, administered
  by every seeded fund-level staff user;
- working regulatory defaults and a PAYE table — both still to be confirmed.

    python -m app.seed      (from backend/)

Logins are listed in TEST_USERS.md."""
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.fund import BankAccountPurpose, Fund, FundBankAccount, FundTrustee, FundType
from app.models.identity import STAFF_ROLES, UserRole
from app.models.mixins import utcnow
from app.models.period import FundPeriod, PeriodStatus
from app.models.reference import Bank
from app.models.regulatory import RegulatoryParameterVersion, TaxBand, TaxTable, TaxTableKind
from app.models.scheme import Scheme, SchemeOfficer
from app.services import fund_access, identity

DEV_PASSWORD = "Pensionz2026"

USERS: list[tuple[str, str, list[UserRole]]] = [
    ("admin@pensionz.dev", "Ada Admin", [UserRole.admin]),
    ("admin2@pensionz.dev", "Ben Admin", [UserRole.admin]),
    ("config.maker@pensionz.dev", "Chikondi Setup", [UserRole.scheme_config_maker]),
    ("config.checker@pensionz.dev", "Dalitso Setup-Checker", [UserRole.scheme_config_checker]),
    ("members@pensionz.dev", "Esther Members", [UserRole.member_admin]),
    ("members.checker@pensionz.dev", "Felix Members-Checker", [UserRole.member_checker]),
    ("contributions@pensionz.dev", "Grace Contributions", [UserRole.contributions_officer]),
    ("contributions.checker@pensionz.dev", "Hastings Contributions-Checker", [UserRole.contributions_checker]),
    ("benefits@pensionz.dev", "Ida Benefits", [UserRole.benefits_officer]),
    ("benefits.checker@pensionz.dev", "James Benefits-Checker", [UserRole.benefits_checker]),
    ("benefits.l2@pensionz.dev", "Kondwani Benefits-L2", [UserRole.benefits_approver_l2]),
    ("finance@pensionz.dev", "Linda Finance", [UserRole.finance]),
    ("finance.checker@pensionz.dev", "Mphatso Finance-Checker", [UserRole.finance_checker]),
    ("payroll@pensionz.dev", "Ndaona Payroll", [UserRole.payroll_officer]),
    ("compliance@pensionz.dev", "Owen Compliance", [UserRole.compliance]),
    ("rm@pensionz.dev", "Pemphero Relationships", [UserRole.relationship_manager]),
    ("auditor@pensionz.dev", "Queen Auditor", [UserRole.auditor]),
    ("trustee@pensionz.dev", "Ruth Trustee", [UserRole.trustee]),
    ("po@pensionz.dev", "Steve Principal-Officer", [UserRole.principal_officer]),
    ("member@pensionz.dev", "Tiwonge Member", [UserRole.member]),
    ("individual@pensionz.dev", "Upile Individual", [UserRole.individual]),
]


def seed_users(db) -> int:
    created = 0
    for email, name, roles in USERS:
        user = identity.find_by_email(db, email)
        if user is None:
            user = identity.create_user(db, email, DEV_PASSWORD, roles, full_name=name)
            created += 1
        # Seed users have a known password, so they aren't "awaiting setup" (no invitation was sent).
        if user.password_changed_at is None:
            user.password_changed_at = utcnow()
    return created


# Invented funds — no real organisation's name. (code, name, type, bank, account no., trustees)
FUNDS = [
    ("UMB01", "Chitukuko Umbrella Pension Fund", FundType.umbrella_dc, "National Bank of Malawi", "1001234567",
     [("Mercy Banda", "Chairperson"), ("Peter Phiri", "Employer-appointed trustee"), ("Alinafe Chirwa", "Member-elected trustee")]),
    ("LSS01", "Lakeshore Sugar Staff Pension Fund", FundType.standalone_dc, "Standard Bank Malawi", "0140987654",
     [("John Mwale", "Chairperson"), ("Chisomo Kachingwe", "Member-elected trustee")]),
    ("MTDB1", "Mulunguzi Teachers Defined Benefit Scheme", FundType.defined_benefit, "FDH Bank", "2200456789",
     [("Grace Nkhoma", "Chairperson"), ("Yamikani Gondwe", "Trustee")]),
    ("PPF01", "Tsogolo Personal Pension Fund", FundType.personal_pension, "NBS Bank", "3300112233",
     [("Hannah Kumwenda", "Chairperson")]),
]


def seed_funds(db) -> int:
    created = 0
    for code, name, fund_type, bank_name, account_no, trustees in FUNDS:
        if db.execute(select(Fund).where(Fund.code == code)).scalar_one_or_none() is not None:
            continue
        bank = db.execute(select(Bank).where(Bank.name == bank_name)).scalar_one()
        branch = next((b for b in bank.branches if b.name == "Blantyre"), None)
        fund = Fund(
            code=code, name=name, fund_type=fund_type, registration_number=f"RBM/PF/{100 + created}",
            tpin=f"7000{created + 1}234", financial_year_end_month=12,
            address_line1="Private Bag 1", address_line2="Victoria Avenue", address_line3="Blantyre",
            phone="+265 1 820 000", email=f"{code.lower()}@funds.example",
            contact_name=trustees[0][0], contact_email=f"secretary.{code.lower()}@funds.example", contact_phone="+265 999 000 000",
        )
        db.add(fund)
        db.flush()
        for order, (trustee, designation) in enumerate(trustees):
            db.add(FundTrustee(fund_id=fund.id, full_name=trustee, designation=designation, appointed_on=date(2024, 1, 1), sort_order=order))
        db.add(FundBankAccount(fund_id=fund.id, bank_id=bank.id, branch_id=branch.id if branch else None,
                               account_name=f"{name} — Collections", account_number=account_no,
                               purpose=BankAccountPurpose.collections))
        created += 1
    db.flush()
    return created


def grant_seed_access(db) -> None:
    """Seeded fund-level staff administer every seeded fund (admins/auditors see all anyway)."""
    fund_ids = [f.id for f in db.execute(select(Fund).where(Fund.code.in_([c for c, *_ in FUNDS]))).scalars()]
    for email, _, roles in USERS:
        if not any(r in STAFF_ROLES for r in roles) or UserRole.admin in roles or UserRole.auditor in roles:
            continue
        user = identity.find_by_email(db, email)
        for fund_id in fund_ids:
            fund_access.grant(db, user.id, fund_id, None)


# Invented participating employers: (fund code, code, name, contribution day, principal officer email or None)
SCHEMES = [
    ("UMB01", "CTE01", "Chikwawa Tea Estates Ltd", 14, "po@pensionz.dev"),
    ("UMB01", "NBL01", "Nkhata Bay Logistics Ltd", 10, None),
    ("LSS01", "LSC01", "Lakeshore Sugar Company Ltd", 14, "po@pensionz.dev"),
    ("MTDB1", "MET01", "Mulunguzi Education Trust", 7, None),
]


def seed_schemes(db) -> None:
    for fund_code, code, name, day, officer_email in SCHEMES:
        fund = db.execute(select(Fund).where(Fund.code == fund_code)).scalar_one()
        if db.execute(select(Scheme.id).where(Scheme.fund_id == fund.id, Scheme.code == code)).first() is not None:
            continue
        scheme = Scheme(fund_id=fund.id, code=code, name=name, contribution_day=day, join_date=date(2024, 1, 1),
                        address_line1="P.O. Box 100", address_line2="Blantyre", contact_name="Human Resources Manager",
                        contact_email=f"hr@{code.lower()}.example", contact_phone="+265 888 000 000")
        db.add(scheme)
        db.flush()
        if officer_email:
            scheme.officers.append(SchemeOfficer(user_id=identity.find_by_email(db, officer_email).id))


# Working defaults until confirmed (TASKS.md → Open decisions → "Regulatory figures").
REGULATORY_DEFAULTS = {
    "min_employee_contribution_pct": "5", "min_employer_contribution_pct": "10", "max_lump_sum_pct": "50",
    "min_retirement_age": "50", "max_retirement_age": "70", "unemployment_access_wait_months": "3",
    "pre_retirement_access_years": "5", "pre_retirement_access_max_pct": "50",
}
REGULATORY_FROM = date(2023, 1, 1)
# Monthly PAYE bands as understood for 2024 — TO CONFIRM with MRA before any real use.
PAYE_BANDS = [("0", "0"), ("150000", "25"), ("500000", "30"), ("2550000", "35")]


def seed_regulatory(db) -> None:
    for key, value in REGULATORY_DEFAULTS.items():
        if db.execute(select(RegulatoryParameterVersion.id).where(RegulatoryParameterVersion.key == key)).first() is None:
            db.add(RegulatoryParameterVersion(key=key, value=Decimal(value), effective_from=REGULATORY_FROM,
                                              source="Dev seed — working default, to confirm (Pension Act 2023)"))
    if db.execute(select(TaxTable.id).where(TaxTable.kind == TaxTableKind.paye_monthly)).first() is None:
        table = TaxTable(kind=TaxTableKind.paye_monthly, effective_from=date(2024, 4, 1), source="Dev seed — to confirm with MRA")
        table.bands = [TaxBand(position=i, lower=Decimal(lo), rate_pct=Decimal(rate)) for i, (lo, rate) in enumerate(PAYE_BANDS)]
        db.add(table)


# PPF01 is left without a processing month, to show that state.
OPEN_MONTH = date(2026, 11, 1)


def seed_periods(db) -> None:
    for code in ("UMB01", "LSS01", "MTDB1"):
        fund = db.execute(select(Fund).where(Fund.code == code)).scalar_one()
        if db.execute(select(FundPeriod.id).where(FundPeriod.fund_id == fund.id)).first() is None:
            db.add(FundPeriod(fund_id=fund.id, period=OPEN_MONTH, status=PeriodStatus.open, opened_at=utcnow()))


def main() -> None:
    with SessionLocal() as db:
        created = seed_users(db)
        funds = seed_funds(db)
        grant_seed_access(db)
        seed_periods(db)
        seed_schemes(db)
        seed_regulatory(db)
        db.commit()
    print(f"Seed complete: {created} user(s), {funds} fund(s) created (password for all: {DEV_PASSWORD}).")


if __name__ == "__main__":
    main()
