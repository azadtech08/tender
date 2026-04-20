"""Authentication router."""

import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    TokenResponse,
    UserCredentials,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from config import settings
from database import get_db
from db_models import User

router = APIRouter()


@router.post("/register", response_model=TokenResponse)
async def register(
    credentials: UserCredentials,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Register a new user."""
    # Check if user already exists
    result = await db.execute(
        User.__table__.select().where(User.email == credentials.email)
    )
    existing_user = result.mappings().one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    hashed_password = get_password_hash(credentials.password)
    new_user = User(
        email=credentials.email,
        password_hash=hashed_password,
        tenant_id=str(uuid.uuid4()),  # Generate tenant_id for new user
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    # Create access token
    access_token_expires = timedelta(hours=settings.jwt_expiration_hours)
    access_token = create_access_token(
        data={
            "sub": str(new_user.id),
            "email": new_user.email,
            "tenant_id": new_user.tenant_id,
        },
        expires_delta=access_token_expires,
    )

    return TokenResponse(access_token=access_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate user and return access token."""
    # Find user by email
    result = await db.execute(
        User.__table__.select().where(User.email == form_data.username)
    )
    user = result.mappings().one_or_none()

    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token_expires = timedelta(hours=settings.jwt_expiration_hours)
    access_token = create_access_token(
        data={
            "sub": str(user["id"]),
            "email": user["email"],
            "tenant_id": user["tenant_id"],
        },
        expires_delta=access_token_expires,
    )

    return TokenResponse(access_token=access_token)


@router.get("/me")
async def read_users_me(current_user: Annotated[dict, Depends(get_current_user)]):
    """Get current user information."""
    return {
        "user_id": current_user.user_id,
        "email": current_user.email,
        "tenant_id": current_user.tenant_id,
    }