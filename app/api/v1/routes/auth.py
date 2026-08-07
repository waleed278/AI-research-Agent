from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import enforce_login_rate_limit, get_current_user, get_db_session
from app.db.models import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=201,
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def signup(
    body: SignupRequest, session: AsyncSession = Depends(get_db_session)
) -> TokenResponse:
    return await auth_service.signup(session, body)


@router.post(
    "/login", response_model=TokenResponse, dependencies=[Depends(enforce_login_rate_limit)]
)
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    return await auth_service.login(session, body)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, created_at=user.created_at)
