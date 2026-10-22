import time

import redis.asyncio as redis
from django.conf import settings
from fastapi import Depends, HTTPException, status

from apps.accounts.models import User
from llm_service.auth import get_current_user

_redis = redis.from_url(settings.CELERY_BROKER_URL, db=1, decode_responses=True)


def rate_limit(scope: str, limit: int, window_seconds: int):

    async def _dependency(user: User = Depends(get_current_user)) -> None:
        window = int(time.time()) // window_seconds
        key = f"ratelimit:{scope}:{user.uuid}:{window}"

        current = await _redis.incr(key)
        if current == 1:
            await _redis.expire(key, window_seconds)

        if current > limit:
            ttl = await _redis.ttl(key)
            retry_after = max(ttl, 0)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded ({limit}/{window_seconds}s). Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

    return _dependency
