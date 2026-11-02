"""One-time codes (FR-PRT-006, FR-SEC-004).

Portal users (principal officers, members, individuals, trustees) without a
staff role enter a 6-digit code at every sign-in (decided 2026-11-02); the
same service will confirm money-affecting portal actions (purpose = the
action, e.g. "remittance"). Codes go by email until an SMS gateway is chosen.

- Only an HMAC of the code is stored; a new code voids the older ones for the
  same purpose; a code works once, for `otp_minutes`.
- `otp_max_attempts` wrong tries kill the code; at most
  `otp_max_sends_per_15_minutes` codes per user per 15 minutes.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.identity import PORTAL_ROLES, OneTimeCode, User
from app.models.mixins import utcnow
from app.services import audit, notifications

SIGN_IN = "sign_in"


def required_at_sign_in(user: User) -> bool:
    return not user.is_staff and any(role in PORTAL_ROLES for role in user.roles)


def _hash(user: User, purpose: str, code: str) -> str:
    message = f"{user.id}:{purpose}:{code}".encode()
    return hmac.new(settings.jwt_secret_key.encode(), message, hashlib.sha256).hexdigest()


def masked_destination(user: User) -> str:
    """Where the code went, without giving the address away: "s•••@example.com"."""
    local, _, domain = user.email.partition("@")
    return f"{local[:1]}•••@{domain}"


def send(db: Session, user: User, purpose: str, reason: str) -> None:
    """Issues and sends a new code. Does not commit."""
    now = utcnow()
    recent = db.execute(
        select(func.count(OneTimeCode.id)).where(OneTimeCode.user_id == user.id, OneTimeCode.created_at >= now - timedelta(minutes=15))
    ).scalar_one()
    if recent >= settings.otp_max_sends_per_15_minutes:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "You have asked for too many codes. Wait 15 minutes and try again.")
    for row in db.execute(
        select(OneTimeCode).where(OneTimeCode.user_id == user.id, OneTimeCode.purpose == purpose, OneTimeCode.used_at.is_(None))
    ).scalars():
        row.used_at = now
    code = f"{secrets.randbelow(10 ** 6):06d}"
    db.add(OneTimeCode(user_id=user.id, purpose=purpose, code_hash=_hash(user, purpose, code), channel="email",
                       expires_at=now + timedelta(minutes=settings.otp_minutes), created_at=now))
    notifications.notify_one_time_code(db, user, code, settings.otp_minutes, reason)
    audit.record(db, user.id, "user", user.id, "one_time_code_sent", after={"purpose": purpose})


def verify(db: Session, user: User, purpose: str, code: str) -> None:
    """Uses up the code or raises 400. A wrong try is committed (it counts
    even though the request fails); success does not commit."""
    row = db.execute(
        select(OneTimeCode).where(OneTimeCode.user_id == user.id, OneTimeCode.purpose == purpose, OneTimeCode.used_at.is_(None))
        .order_by(OneTimeCode.created_at.desc()).limit(1).with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This code has already been used or replaced — ask for a new one")
    if row.expires_at <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This code has expired — ask for a new one")
    if row.attempts >= settings.otp_max_attempts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Too many wrong codes — ask for a new one")
    if not hmac.compare_digest(row.code_hash, _hash(user, purpose, code.strip())):
        row.attempts += 1
        left = settings.otp_max_attempts - row.attempts
        if left == 0:
            row.used_at = utcnow()
        audit.record(db, user.id, "user", user.id, "one_time_code_wrong", after={"purpose": purpose})
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "That code isn't right — " + (f"{left} tries left" if left else "ask for a new one"))
    row.used_at = utcnow()
