"""Auth router: login, register, and token refresh."""
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import hash_password, verify_password, create_access_token
from app.auth.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User, Tenant

router = APIRouter()

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


_ALLOWED_SELF_REGISTER_ROLES = {"advisor"}  # admin/compliance assigned by an existing admin


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str = ""
    role: str = "advisor"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("password must be at least 12 characters")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in _ALLOWED_SELF_REGISTER_ROLES:
            raise ValueError(f"role must be one of: {sorted(_ALLOWED_SELF_REGISTER_ROLES)}")
        return v


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    tenant_id: str


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Authenticate and return a JWT token."""
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id)})
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        role=user.role,
        tenant_id=str(user.tenant_id),
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user under the default tenant."""
    existing = await db.execute(select(User).where(User.email == request.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    # Ensure default tenant exists
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.id == uuid.UUID(DEFAULT_TENANT_ID))
    )
    if not tenant_result.scalar_one_or_none():
        db.add(Tenant(id=uuid.UUID(DEFAULT_TENANT_ID), name="Default Tenant"))
        await db.commit()

    user = User(
        tenant_id=uuid.UUID(DEFAULT_TENANT_ID),
        email=request.email,
        hashed_password=hash_password(request.password),
        full_name=request.full_name,
        role=request.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": str(user.tenant_id)})
    return TokenResponse(
        access_token=token,
        user_id=str(user.id),
        role=user.role,
        tenant_id=str(user.tenant_id),
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Return current authenticated user info."""
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role,
        "tenant_id": str(current_user.tenant_id),
    }
