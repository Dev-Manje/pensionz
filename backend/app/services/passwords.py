"""Sign-in, passwords and invitations (FR-SEC-004).

- Sign-in locks the account for `lockout_minutes` after `max_failed_logins`
  wrong passwords in a row.
- Forgot password: same answer whether or not the address has an account; the
  emailed link works once, for 1 hour; only its SHA-256 is stored.
- Invitations: staff create a login and the person sets their own password
  from a 7-day link — staff never choose or see it.
- Setting a password stamps `password_changed_at`, which signs out every
  other session (tokens issued before it are refused).
- Portal users also enter a one-time code at every sign-in (`services/otp.py`):
  the right password (or a new password from a link) only sends the code;
  `complete_sign_in` runs once the code is confirmed.
"""
import hashlib
import re
import secrets
import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models.identity import PasswordResetToken, User, UserStatus
from app.models.mixins import utcnow
from app.services import audit, identity, notifications, otp

RESET_HOURS = 1
STAFF_RESET_HOURS = 24
INVITE_DAYS = 7
MAX_RESET_REQUESTS_PER_HOUR = 3


def _bad(detail: str, code: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=code, detail=detail)


def check_policy(password: str, email: str | None = None) -> None:
    """At least 8 characters, with a letter and a number, and not the email."""
    if len(password) < 8:
        raise _bad("Use at least 8 characters for the password")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise _bad("The password needs at least one letter and one number")
    if email and password.strip().lower() == email.strip().lower():
        raise _bad("The password can't be your email address")


def authenticate(db: Session, email: str, password: str, ip_address: str | None = None) -> User:
    """Returns the user or raises 401/403/423. Commits the attempt's outcome."""
    user = identity.find_by_email(db, email)
    now = utcnow()
    if user is not None and user.locked_until is not None and user.locked_until > now:
        raise _bad("Too many wrong passwords. Try again later or reset your password.", status.HTTP_423_LOCKED)
    if user is None or not verify_password(password, user.password_hash):
        if user is not None:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.max_failed_logins:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_login_count = 0
                audit.record(db, None, "user", user.id, "locked_out", ip_address=ip_address)
            db.commit()
        raise _bad("Invalid email or password", status.HTTP_401_UNAUTHORIZED)
    if user.status != UserStatus.active:
        raise _bad(f"This account is not active. Contact {settings.brand_administrator}.", status.HTTP_403_FORBIDDEN)
    user.failed_login_count = 0
    user.locked_until = None
    if otp.required_at_sign_in(user):
        otp.send(db, user, otp.SIGN_IN, "sign in")
        audit.record(db, user.id, "user", user.id, "password_accepted", ip_address=ip_address)
    else:
        _record_sign_in(db, user, ip_address)
    db.commit()
    return user


def _record_sign_in(db: Session, user: User, ip_address: str | None) -> None:
    user.last_login_at = utcnow()
    audit.record(db, user.id, "user", user.id, "signed_in", ip_address=ip_address)


def complete_sign_in(db: Session, user: User, code: str, ip_address: str | None = None) -> User:
    """Second step for portal users: the emailed code. Commits."""
    if user.locked_until is not None and user.locked_until > utcnow():
        raise _bad("Too many wrong passwords. Try again later or reset your password.", status.HTTP_423_LOCKED)
    otp.verify(db, user, otp.SIGN_IN, code)
    _record_sign_in(db, user, ip_address)
    db.commit()
    return user


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _set_password(db: Session, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    user.password_changed_at = utcnow()
    user.failed_login_count = 0
    user.locked_until = None
    for row in db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)):
        row.used_at = user.password_changed_at


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise _bad("Your current password isn't right")
    if current_password == new_password:
        raise _bad("Choose a password different from your current one")
    check_policy(new_password, user.email)
    _set_password(db, user, new_password)
    audit.record(db, user.id, "user", user.id, "password_changed")
    notifications.notify_password_changed(db, user, "changed")
    db.commit()


def issue_token(db: Session, user: User, purpose: str, created_by: uuid.UUID | None) -> str:
    """A new single-use link (voids older ones). Does not commit."""
    now = utcnow()
    for row in db.query(PasswordResetToken).filter(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)):
        row.used_at = now
    token = secrets.token_urlsafe(32)
    if purpose == "invite":
        lifetime = timedelta(days=INVITE_DAYS)
    else:
        lifetime = timedelta(hours=STAFF_RESET_HOURS if created_by else RESET_HOURS)
    db.add(PasswordResetToken(user_id=user.id, token_hash=_hash(token), purpose=purpose,
                              expires_at=now + lifetime, created_by_user_id=created_by))
    return token


def request_reset(db: Session, email: str) -> None:
    """Self-service "forgot password". Silent whatever happens."""
    user = identity.find_by_email(db, email)
    if user is None or user.status != UserStatus.active:
        return
    recent = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == user.id, PasswordResetToken.created_at >= utcnow() - timedelta(hours=1))
        .count()
    )
    if recent >= MAX_RESET_REQUESTS_PER_HOUR:
        return
    token = issue_token(db, user, "reset", None)
    audit.record(db, None, "user", user.id, "password_reset_requested")
    notifications.notify_password_reset_link(db, user, token, RESET_HOURS)
    db.commit()


def _valid_row(db: Session, token: str) -> PasswordResetToken | None:
    row = db.query(PasswordResetToken).filter(PasswordResetToken.token_hash == _hash(token)).first()
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        return None
    user = db.get(User, row.user_id)
    if user is None or user.status != UserStatus.active:
        return None
    return row


def link_status(db: Session, token: str) -> dict:
    row = _valid_row(db, token)
    return {"valid": row is not None, "purpose": row.purpose if row else None,
            "email": db.get(User, row.user_id).email if row else None}


def reset_password(db: Session, token: str, new_password: str) -> User:
    """Sets the password; signs staff in, sends portal users a sign-in code."""
    row = _valid_row(db, token)
    if row is None:
        raise _bad("This link has expired or was already used — ask for a new one")
    user = db.get(User, row.user_id)
    check_policy(new_password, user.email)
    _set_password(db, user, new_password)
    row.used_at = user.password_changed_at
    audit.record(db, None, "user", user.id, "password_set" if row.purpose == "invite" else "password_reset")
    if otp.required_at_sign_in(user):
        otp.send(db, user, otp.SIGN_IN, "sign in")
    else:
        user.last_login_at = utcnow()
    notifications.notify_password_changed(db, user, "set" if row.purpose == "invite" else "reset")
    db.commit()
    db.refresh(user)
    return user
