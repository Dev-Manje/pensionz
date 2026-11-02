import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token, create_token, decode_token, issued_before_password_change
from app.models.identity import User, UserStatus
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    ResendCodeRequest,
    ResetLinkStatus,
    ResetPasswordRequest,
    SignInCodeRequest,
    SignInResult,
    TokenPair,
)
from app.services import otp, passwords

CHALLENGE = "sign_in_challenge"

router = APIRouter(prefix="/auth", tags=["auth"])


def _tokens(user: User) -> TokenPair:
    subject = str(user.id)
    return TokenPair(access_token=create_access_token(subject), refresh_token=create_refresh_token(subject))


def _sign_in_result(user: User) -> SignInResult:
    """Tokens, or for portal users the challenge to finish with the code
    `passwords` has just sent (FR-PRT-006: a code at every portal sign-in)."""
    if otp.required_at_sign_in(user):
        challenge = create_token(str(user.id), timedelta(minutes=settings.otp_minutes), CHALLENGE)
        return SignInResult(code_required=True, challenge=challenge, code_sent_to=otp.masked_destination(user))
    return SignInResult(**_tokens(user).model_dump())


def _challenged_user(db: Session, challenge: str) -> User:
    data = decode_token(challenge)
    if data is None or data.get("type") != CHALLENGE:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This sign-in has timed out — enter your email and password again")
    user = db.get(User, uuid.UUID(data["sub"]))
    if user is None or user.status != UserStatus.active or issued_before_password_change(data, user.password_changed_at):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "This sign-in has timed out — enter your email and password again")
    return user


@router.post("/login", response_model=SignInResult)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> SignInResult:
    # No self-registration: staff and portal users are invited (FR-PRT-006).
    return _sign_in_result(passwords.authenticate(db, payload.email, payload.password, client_ip(request)))


@router.post("/sign-in-code", response_model=TokenPair)
def sign_in_code(payload: SignInCodeRequest, request: Request, db: Session = Depends(get_db)) -> TokenPair:
    """Second step for portal users: the one-time code from the email."""
    user = _challenged_user(db, payload.challenge)
    return _tokens(passwords.complete_sign_in(db, user, payload.code, client_ip(request)))


@router.post("/sign-in-code/resend", status_code=status.HTTP_202_ACCEPTED)
def resend_sign_in_code(payload: ResendCodeRequest, db: Session = Depends(get_db)) -> dict:
    user = _challenged_user(db, payload.challenge)
    otp.send(db, user, otp.SIGN_IN, "sign in")
    db.commit()
    return {"detail": f"A new code is on its way to {otp.masked_destination(user)}"}


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    data = decode_token(payload.refresh_token)
    if data is None or data.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    user = db.get(User, uuid.UUID(data["sub"]))
    if user is None or user.status != UserStatus.active or issued_before_password_change(data, user.password_changed_at):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return _tokens(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> None:
    return None


@router.post("/change-password", response_model=TokenPair)
def change_password(payload: ChangePasswordRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> TokenPair:
    """Signs out every other session; this one carries on with the new tokens."""
    passwords.change_password(db, user, payload.current_password, payload.new_password)
    return _tokens(user)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(payload: ForgotPasswordRequest, db: Session = Depends(get_db)) -> dict:
    passwords.request_reset(db, payload.email)
    return {"detail": "If that email has an account, a link to reset the password is on its way."}


@router.get("/reset-password/status", response_model=ResetLinkStatus)
def reset_link_status(token: str, db: Session = Depends(get_db)) -> dict:
    return passwords.link_status(db, token)


@router.post("/reset-password", response_model=SignInResult)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> SignInResult:
    """Sets the password and signs the user in (portal users: after the code)."""
    return _sign_in_result(passwords.reset_password(db, payload.token, payload.new_password))


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)) -> User:
    return user
