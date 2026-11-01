from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.identity import User, UserRole, UserRoleAssignment


def find_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(func.lower(User.email) == email.strip().lower()).first()


def create_user(
    db: Session, email: str, password: str, roles: list[UserRole], *, full_name: str = "", phone: str | None = None
) -> User:
    """A user and their roles are always created together. Does not commit."""
    user = User(email=email.strip().lower(), password_hash=hash_password(password), full_name=full_name, phone=phone)
    db.add(user)
    db.flush()
    for role in roles:
        db.add(UserRoleAssignment(user_id=user.id, role=role))
    db.flush()
    db.refresh(user)
    return user


def set_roles(db: Session, user: User, roles: list[UserRole]) -> None:
    """Replaces the user's roles with exactly `roles`. Does not commit."""
    wanted = set(roles)
    for assignment in list(user.role_assignments):
        if assignment.role not in wanted:
            user.role_assignments.remove(assignment)
    existing = {a.role for a in user.role_assignments}
    for role in wanted - existing:
        user.role_assignments.append(UserRoleAssignment(role=role))
    db.flush()
