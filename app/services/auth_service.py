from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.core.jwt import create_access_token
from app.core.security import hash_password, verify_password
from app.db.models import User
from app.db.repositories import UserRepository
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse


async def signup(
    session: AsyncSession, request: SignupRequest, settings: Settings | None = None
) -> TokenResponse:
    settings = settings or get_settings()
    users = UserRepository(session)
    if await users.get_by_email(request.email) is not None:
        raise ConflictError("An account with this email already exists.")

    user = await users.create(email=request.email, password_hash=hash_password(request.password))
    return _issue_token(user, settings)


async def login(
    session: AsyncSession, request: LoginRequest, settings: Settings | None = None
) -> TokenResponse:
    settings = settings or get_settings()
    user = await UserRepository(session).get_by_email(request.email)
    # Deliberately identical error for "no such user" and "wrong password"
    # -- distinguishing them lets an attacker enumerate registered emails.
    if user is None or not user.is_active or not verify_password(request.password, user.password_hash):
        raise UnauthorizedError("Incorrect email or password.")

    return _issue_token(user, settings)


def _issue_token(user: User, settings: Settings) -> TokenResponse:
    token = create_access_token(user.id, user.email, settings)
    return TokenResponse(
        access_token=token,
        user=UserResponse(id=user.id, email=user.email, created_at=user.created_at),
    )
