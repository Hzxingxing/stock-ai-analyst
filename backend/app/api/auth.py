from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.config import settings
from app.db.models import User
from app.db.session import get_session
from app.security import (
    DUMMY_PASSWORD_HASH,
    SESSION_COOKIE,
    create_session_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)


class UserView(BaseModel):
    id: str
    email: EmailStr
    created_at: str


def _user_view(user: User) -> UserView:
    created_at = (
        user.created_at.replace(tzinfo=UTC).isoformat()
        if user.created_at.tzinfo is None
        else user.created_at.isoformat()
    )
    return UserView(id=user.id, email=user.email, created_at=created_at)


def _set_session_cookie(response: Response, user_id: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session_token(user_id),
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        max_age=settings.auth_token_hours * 60 * 60,
        path="/api",
    )


@router.post("/register", response_model=UserView, status_code=status.HTTP_201_CREATED)
async def register(
    credentials: Credentials,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> UserView:
    email = str(credentials.email).strip().lower()
    existing = await session.scalar(select(User.id).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="该邮箱已注册")
    user = User(email=email, password_hash=hash_password(credentials.password))
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="该邮箱已注册") from exc
    await session.refresh(user)
    _set_session_cookie(response, user.id)
    return _user_view(user)


@router.post("/login", response_model=UserView)
async def login(
    credentials: Credentials,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> UserView:
    email = str(credentials.email).strip().lower()
    user = await session.scalar(select(User).where(User.email == email))
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    valid = verify_password(credentials.password, password_hash)
    if user is None or not valid or not user.is_active:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    _set_session_cookie(response, user.id)
    return _user_view(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    response.delete_cookie(
        SESSION_COOKIE,
        path="/api",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserView)
async def me(user: User = Depends(get_current_user)) -> UserView:
    return _user_view(user)
