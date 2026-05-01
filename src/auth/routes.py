import secrets
from datetime import datetime, timedelta, timezone
from typing import cast

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
    OAuth2PasswordRequestForm,
)
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.auth.dependencies import get_current_user
from src.auth.security import hash_password, verify_password
from src.config.settings import get_settings
from src.database.models import (
    ActivationToken,
    PasswordResetToken,
    RefreshToken,
    RevokedAccessToken,
    User,
    UserGroup,
    UserGroupEnum,
)
from src.database.session import get_db
from src.schemas.auth import (
    ChangePasswordRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    ResendActivationRequest,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
_optional_bearer = HTTPBearer(auto_error=False)

ACCESS_TOKEN_TTL = timedelta(minutes=30)
REFRESH_TOKEN_TTL = timedelta(days=7)
ACTIVATION_TOKEN_TTL = timedelta(hours=24)
RESET_TOKEN_TTL = timedelta(hours=24)


def _expires_at_utc(expires_at: datetime) -> datetime:
    """Normalize stored expiry to aware UTC ``datetime`` for comparisons."""
    if expires_at.tzinfo is None:
        return expires_at.replace(tzinfo=timezone.utc)
    return expires_at.astimezone(timezone.utc)


def _make_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + ACCESS_TOKEN_TTL
    jti = secrets.token_urlsafe(16)
    return jwt.encode(
        {"sub": str(user_id), "exp": expire, "jti": jti},
        settings.SECRET_KEY,
        algorithm="HS256",
    )


async def _get_or_create_user_group(db: AsyncSession) -> UserGroup:
    result = await db.execute(
        select(UserGroup).where(UserGroup.name == UserGroupEnum.USER)
    )
    group = result.scalar_one_or_none()
    if not group:
        group = UserGroup(name=UserGroupEnum.USER)
        db.add(group)
        await db.flush()
    return group


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    group = await _get_or_create_user_group(db)
    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        is_active=False,
        group_id=group.id,
    )
    db.add(user)
    await db.flush()

    token = ActivationToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + ACTIVATION_TOKEN_TTL,
    )
    db.add(token)
    await db.commit()

    from src.worker.mail_tasks import send_activation_email

    send_activation_email.delay(data.email, token.token)  # type: ignore[attr-defined]

    payload: dict = {
        "detail": "Registered. Check your email to activate your account.",
    }
    if settings.EXPOSE_DEV_AUTH_TOKENS:
        payload["activation_token"] = token.token
    return payload


async def _perform_activation(token: str, db: AsyncSession) -> dict:
    result = await db.execute(
        select(ActivationToken).where(ActivationToken.token == token)
    )
    activation = result.scalar_one_or_none()

    if not activation:
        raise HTTPException(status_code=404, detail="Invalid activation token")
    exp = cast(datetime, activation.expires_at)
    if _expires_at_utc(exp) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Activation token expired")

    user = await db.get(User, activation.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    await db.delete(activation)
    await db.commit()
    return {"detail": "Account activated successfully"}


@router.post("/activate/{token}")
async def activate_account_post(token: str, db: AsyncSession = Depends(get_db)):
    return await _perform_activation(token, db)


@router.get("/activate/{token}")
async def activate_account_get(token: str, db: AsyncSession = Depends(get_db)):
    """Same as POST — for activation links opened from email (browser GET)."""
    return await _perform_activation(token, db)


@router.post("/resend-activation")
async def resend_activation(
    data: ResendActivationRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if not user or user.is_active:
        # Do not reveal whether the email is registered
        msg = "If this email exists and is not activated, " "a new link has been sent."
        return {"detail": msg}

    # Remove previous activation token if present
    old = await db.execute(
        select(ActivationToken).where(ActivationToken.user_id == user.id)
    )
    old_token = old.scalar_one_or_none()
    if old_token:
        await db.delete(old_token)

    token = ActivationToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        expires_at=datetime.now(timezone.utc) + ACTIVATION_TOKEN_TTL,
    )
    db.add(token)
    await db.commit()

    from src.worker.mail_tasks import send_activation_email

    send_activation_email.delay(user.email, token.token)  # type: ignore[attr-defined]

    msg = "If this email exists and is not activated, " "a new link has been sent."
    payload = {"detail": msg}
    if settings.EXPOSE_DEV_AUTH_TOKENS:
        payload["activation_token"] = token.token
    return payload


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is not activated")

    access_token = _make_access_token(user.id)
    refresh_token_str = secrets.token_urlsafe(64)

    refresh_token = RefreshToken(
        user_id=user.id,
        token=refresh_token_str,
        expires_at=datetime.now(timezone.utc) + REFRESH_TOKEN_TTL,
    )
    db.add(refresh_token)
    await db.commit()

    return TokenResponse(access_token=access_token, refresh_token=refresh_token_str)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(data: RefreshRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == data.refresh_token)
    )
    token = result.scalar_one_or_none()

    if not token:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    exp_rt = cast(datetime, token.expires_at)
    if _expires_at_utc(exp_rt) < datetime.now(timezone.utc):
        await db.delete(token)
        await db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    access_token = _make_access_token(token.user_id)
    return TokenResponse(access_token=access_token, refresh_token=data.refresh_token)


@router.post("/logout")
async def logout(
    data: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
):
    """
    Revokes the refresh token. If ``Authorization: Bearer <access>`` is sent,
    the access token is blacklisted until expiry (``.tasks`` logout semantics).
    """
    if credentials and credentials.scheme.lower() == "bearer":
        try:
            payload = jwt.decode(
                credentials.credentials,
                settings.SECRET_KEY,
                algorithms=["HS256"],
            )
            jti = payload.get("jti")
            exp_claim = payload.get("exp")
            if jti and exp_claim is not None:
                exp_dt = datetime.fromtimestamp(int(exp_claim), tz=timezone.utc)
                existing = await db.execute(
                    select(RevokedAccessToken).where(RevokedAccessToken.jti == jti)
                )
                if existing.scalar_one_or_none() is None:
                    db.add(RevokedAccessToken(jti=jti, expires_at=exp_dt))
        except JWTError:
            pass

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token == data.refresh_token)
    )
    token = result.scalar_one_or_none()
    if token:
        await db.delete(token)
        await db.commit()
    else:
        await db.commit()
    return {"detail": "Logged out successfully"}


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    current_user.hashed_password = hash_password(data.new_password)
    await db.commit()
    return {"detail": "Password changed successfully"}


@router.post("/forgot-password")
async def forgot_password(
    data: PasswordResetRequest, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    if user and user.is_active:
        # Remove previous reset token if present
        old = await db.execute(
            select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
        )
        old_token = old.scalar_one_or_none()
        if old_token:
            await db.delete(old_token)

        token = PasswordResetToken(
            user_id=user.id,
            token=secrets.token_urlsafe(32),
            expires_at=datetime.now(timezone.utc) + RESET_TOKEN_TTL,
        )
        db.add(token)
        await db.commit()

        from src.worker.mail_tasks import send_password_reset_email

        send_password_reset_email.delay(  # type: ignore[attr-defined]
            user.email,
            token.token,
        )

    return {"detail": ("If this email is registered, a reset link has been sent.")}


@router.post("/reset-password/{token}")
async def reset_password(
    token: str, data: PasswordResetConfirm, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(PasswordResetToken).where(PasswordResetToken.token == token)
    )
    reset = result.scalar_one_or_none()

    if not reset:
        raise HTTPException(status_code=404, detail="Invalid reset token")
    exp_pw = cast(datetime, reset.expires_at)
    if _expires_at_utc(exp_pw) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Reset token expired")

    user = await db.get(User, reset.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = hash_password(data.new_password)
    await db.delete(reset)
    await db.commit()
    return {"detail": "Password reset successfully"}
