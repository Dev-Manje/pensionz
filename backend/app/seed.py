"""Dev seed: one user per role (plus a second admin, so user-access changes
can be approved). Safe to run repeatedly — existing users are left alone.

    docker compose exec backend python -m app.seed

Logins are listed in TEST_USERS.md."""
from app.core.database import SessionLocal
from app.models.identity import UserRole
from app.models.mixins import utcnow
from app.services import identity

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


def main() -> None:
    with SessionLocal() as db:
        created = seed_users(db)
        db.commit()
    print(f"Seed complete: {created} user(s) created (password for all: {DEV_PASSWORD}).")


if __name__ == "__main__":
    main()
