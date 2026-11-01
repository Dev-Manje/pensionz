"""Housekeeping: deletes password links that expired or were used more than
30 days ago (they can never be used again)."""
from datetime import date, timedelta

from sqlalchemy import delete, or_
from sqlalchemy.orm import Session

from app.models.identity import PasswordResetToken
from app.models.mixins import utcnow


def run(db: Session, as_of: date) -> str:
    cutoff = utcnow() - timedelta(days=30)
    result = db.execute(
        delete(PasswordResetToken).where(
            or_(PasswordResetToken.expires_at < cutoff, PasswordResetToken.used_at < cutoff)
        )
    )
    db.commit()
    return f"{result.rowcount} old link(s) removed"
