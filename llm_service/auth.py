"""Shared FastAPI auth dependencies - split out from main.py so other
modules (rate_limit.py) can depend on the authenticated user without a
circular import back into main.py.
"""

from asgiref.sync import sync_to_async
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.authentication.constants import TokenClaims
from apps.accounts.models import User

security = HTTPBearer() #extract and enforce standard HTTP Bearer token authentication (typically JSON Web Tokens, or JWTs) from incoming request headers


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """Validate the JWT Django issued, using the same simplejwt signing
    config - no network call back to Django, since both services share one
    SECRET_KEY and the same Postgres via django.setup() (see main.py).
    `async def` with an explicit sync_to_async bridge for the ORM lookup -
    consistent with every other Django touchpoint in this service.
    """
    try:
        access_token = AccessToken(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from exc

    user_uuid = access_token.get(TokenClaims.USER_UUID)
    if not user_uuid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing user identity"
        )

    try:
        return await sync_to_async(User.objects.get, thread_sensitive=False)(uuid=user_uuid)
    except User.DoesNotExist as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists"
        ) from exc


async def get_manager_or_above_user(user: User = Depends(get_current_user)) -> User:
    """Evaluation inspects AI answer quality across the whole system, not
    just the caller's own conversations - ops-level access, gated a step
    above the plain chat endpoints (which any employee can use)."""
    if user.role not in {User.RoleChoices.ADMIN, User.RoleChoices.MANAGER}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Manager role or above required."
        )
    return user
