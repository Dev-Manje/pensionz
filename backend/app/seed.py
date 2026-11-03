"""Dev seed, safe to run repeatedly (existing rows are left alone):
- one user per role, plus a second admin so user-access changes can be approved;
- four invented funds (umbrella DC, stand-alone DC, DB, personal pension) with
  trustees, a bank account, employers and an open processing month, administered
  by every seeded fund-level staff user;
- working regulatory defaults and a PAYE table — both still to be confirmed;
- nine invented members across the employers (one deferred, one inactive).

    python -m app.seed      (from backend/)

Logins are listed in TEST_USERS.md."""
import os
from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.fund import BankAccountPurpose, Fund, FundBankAccount, FundTrustee, FundType
from app.models.identity import STAFF_ROLES, UserRole
from app.models.mixins import utcnow
from app.models.period import FundPeriod, PeriodStatus
from app.models.category import BenefitCategory, BenefitCategoryTerms, BenefitDesign
from app.models.fee import FeeBasis, FeeFrequency, FeePayer, FeeRule, FeeType
from app.models.investment import InvestmentOption, PricingMethod
from app.models.reference import Bank
from app.models.regulatory import RegulatoryParameterVersion, TaxBand, TaxTable, TaxTableKind
from app.models.scheme import Scheme, SchemeOfficer
from app.services import fund_access, identity

# Every seeded login gets this password; set SEED_PASSWORD to choose another (e.g. on a UAT server).
DEV_PASSWORD = os.environ.get("SEED_PASSWORD") or "Pensionz2026"

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


# Declared-rate pools for the DC and personal funds (the DB fund has none).
OPTIONS = [
    ("UMB01", "GEN", "General Pool"), ("UMB01", "MMK", "Money Market Pool"),
    ("LSS01", "GEN", "General Pool"), ("PPF01", "GEN", "General Pool"),
]


def seed_options(db) -> None:
    for fund_code, code, name in OPTIONS:
        fund = db.execute(select(Fund).where(Fund.code == fund_code)).scalar_one()
        if db.execute(select(InvestmentOption.id).where(InvestmentOption.fund_id == fund.id, InvestmentOption.code == code)).first() is None:
            db.add(InvestmentOption(fund_id=fund.id, code=code, name=name, pricing_method=PricingMethod.declared_rate,
                                    launch_date=date(2024, 1, 1), description="Earns the bonus rate the trustees declare each half-year."))


# (scheme code, category code, name, EE %, ER %, NRA) — DB categories get 1/60 and 36 months.
CATEGORIES = [
    ("CTE01", "MGT", "Management", "7.5", "15", 60), ("CTE01", "STF", "Staff", "5", "10", 60),
    ("NBL01", "ALL", "All employees", "5", "10", 60), ("LSC01", "STF", "Permanent staff", "5", "12", 60),
    ("MET01", "TCH", "Teaching staff", "6", None, 60),
]
VESTING = [{"years": 0, "vested_pct": "0"}, {"years": 2, "vested_pct": "50"}, {"years": 5, "vested_pct": "100"}]


def seed_categories(db) -> None:
    for scheme_code, code, name, ee, er, nra in CATEGORIES:
        scheme = db.execute(select(Scheme).where(Scheme.code == scheme_code)).scalar_one()
        if db.execute(select(BenefitCategory.id).where(BenefitCategory.scheme_id == scheme.id, BenefitCategory.code == code)).first():
            continue
        fund = db.get(Fund, scheme.fund_id)
        category = BenefitCategory(scheme_id=scheme.id, fund_id=fund.id, code=code, name=name)
        db.add(category)
        db.flush()
        is_db = fund.fund_type == FundType.defined_benefit
        option = None if is_db else db.execute(
            select(InvestmentOption).where(InvestmentOption.fund_id == fund.id, InvestmentOption.code == "GEN")).scalar_one()
        db.add(BenefitCategoryTerms(
            category_id=category.id, effective_from=date(2024, 1, 1), design=BenefitDesign.db if is_db else BenefitDesign.dc,
            employee_rate=Decimal(ee), employer_rate=Decimal(er) if er else None, normal_retirement_age=nra,
            min_entry_age=18, max_entry_age=55, waiting_period_months=0 if is_db else 3,
            vesting_scale=[] if is_db else VESTING, default_investment_option_id=option.id if option else None,
            group_life_multiple=Decimal("3"), accrual_denominator=60 if is_db else None, final_salary_months=36 if is_db else None,
        ))


def seed_fees(db) -> None:
    """Illustrative (invented) fees for UMB01: a fund-wide admin fee on contributions, a negotiated
    rate for CTE01, and an investment management fee on assets."""
    fund = db.execute(select(Fund).where(Fund.code == "UMB01")).scalar_one()
    if db.execute(select(FeeRule.id).where(FeeRule.fund_id == fund.id)).first():
        return
    cte = db.execute(select(Scheme).where(Scheme.code == "CTE01")).scalar_one()
    start = date(2024, 1, 1)
    db.add_all([
        FeeRule(fund_id=fund.id, code="ADM", name="Administration fee", fee_type=FeeType.administration, basis=FeeBasis.pct_contributions,
                rate=Decimal("1.5"), payer=FeePayer.member, frequency=FeeFrequency.per_contribution, effective_from=start),
        FeeRule(fund_id=fund.id, scheme_id=cte.id, code="ADM-CTE", name="Administration fee (negotiated)", fee_type=FeeType.administration,
                basis=FeeBasis.pct_contributions, rate=Decimal("1.25"), payer=FeePayer.employer, frequency=FeeFrequency.per_contribution,
                effective_from=start),
        FeeRule(fund_id=fund.id, code="IMF", name="Investment management fee", fee_type=FeeType.investment_management,
                basis=FeeBasis.pct_assets, rate=Decimal("0.75"), payer=FeePayer.fund, frequency=FeeFrequency.monthly, effective_from=start),
    ])


# Invented members: (employer, category, first, last, gender, born, joined, employee no., status).
MEMBERS = [
    ("CTE01", "MGT", "Thoko", "Mwale", "female", date(1978, 3, 14), date(2024, 1, 1), "CT0001", "active"),
    ("CTE01", "STF", "Yamikani", "Phiri", "male", date(1991, 7, 2), date(2024, 1, 1), "CT0102", "active"),
    ("CTE01", "STF", "Chimwemwe", "Banda", "female", date(1995, 11, 23), date(2024, 6, 1), "CT0117", "active"),
    ("CTE01", "STF", "Kondwani", "Gondwe", "male", date(1986, 1, 9), date(2024, 1, 1), "CT0043", "deferred"),
    ("NBL01", "ALL", "Mercy", "Chirwa", "female", date(1983, 5, 30), date(2024, 2, 1), "NB2201", "active"),
    ("NBL01", "ALL", "Blessings", "Nyirenda", "male", date(1999, 9, 17), date(2025, 3, 1), "NB2378", "active"),
    ("LSC01", "STF", "Grace", "Kumwenda", "female", date(1974, 12, 5), date(2024, 1, 1), "LS015", "active"),
    ("LSC01", "STF", "Patrick", "Mbewe", "male", date(1989, 4, 21), date(2024, 1, 1), "LS031", "inactive"),
    ("MET01", "TCH", "Esnart", "Kalua", "female", date(1980, 8, 11), date(2024, 1, 1), "TCH0007", "active"),
]


def seed_members(db) -> None:
    from app.models.member import AssignmentReason, Member, MemberAssignment, MemberStatus, MemberStatusChange
    from app.services.members import _next_account_code, id_key

    for i, (scheme_code, cat_code, first, last, gender, born, joined, emp_no, status) in enumerate(MEMBERS):
        scheme = db.execute(select(Scheme).where(Scheme.code == scheme_code)).scalar_one()
        if db.execute(select(Member.id).where(Member.scheme_id == scheme.id, Member.employee_no == emp_no)).first():
            continue
        category = db.execute(select(BenefitCategory).where(BenefitCategory.scheme_id == scheme.id, BenefitCategory.code == cat_code)).scalar_one()
        fund = db.get(Fund, scheme.fund_id)
        id_number = f"MW{born:%y%m%d}{i:03d}X"
        member = Member(fund_id=fund.id, scheme_id=scheme.id, category_id=category.id, account_code=_next_account_code(db, fund),
                        first_name=first, last_name=last, gender=gender, date_of_birth=born, nationality="MW", id_type="NATID",
                        id_number=id_number, id_number_key=id_key(id_number), employee_no=emp_no, date_joined_fund=joined,
                        date_joined_employer=joined, mobile=f"+265 99{i} 100 {200 + i}", civil_status_current="married",
                        physical_address="Area 47, Lilongwe" if i % 2 else "Namiwawa, Blantyre", status=MemberStatus.active,
                        status_effective=joined, next_of_kin_name=f"{'John' if gender == 'female' else 'Mary'} {last}",
                        next_of_kin_relationship="SPOUSE")
        db.add(member)
        db.flush()
        db.add(MemberAssignment(member_id=member.id, scheme_id=scheme.id, category_id=category.id, effective_from=joined,
                                reason=AssignmentReason.joined))
        db.add(MemberStatusChange(member_id=member.id, from_status=None, to_status=MemberStatus.active, effective_date=joined,
                                  reason="Joined the fund"))
        if status != "active":
            when = date(2026, 6, 30)
            reason = "Resigned" if status == "deferred" else "Unpaid study leave"
            db.add(MemberStatusChange(member_id=member.id, from_status=MemberStatus.active, to_status=MemberStatus(status),
                                      effective_date=when, reason=reason))
            member.status, member.status_effective = MemberStatus(status), when
            if status == "deferred":
                member.exit_date = when


# Working defaults until confirmed (TASKS.md → Open decisions → "Regulatory figures").
REGULATORY_DEFAULTS = {
    "min_employee_contribution_pct": "5", "min_employer_contribution_pct": "10", "max_lump_sum_pct": "50",
    "min_retirement_age": "50", "max_retirement_age": "70", "unemployment_access_wait_months": "3",
    "pre_retirement_access_years": "5", "pre_retirement_access_max_pct": "50",
    "kyc_review_years_high": "1", "kyc_review_years_medium": "2", "kyc_review_years_low": "3",
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


# PPF01 is left without a processing month, to show that state. The open month is the current one.
OPEN_MONTH = date.today().replace(day=1)


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
        seed_options(db)
        seed_categories(db)
        seed_fees(db)
        seed_members(db)
        db.commit()
    print(f"Seed complete: {created} user(s), {funds} fund(s) created (password for all: {DEV_PASSWORD}).")


if __name__ == "__main__":
    main()
