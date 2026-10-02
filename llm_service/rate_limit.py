"""Per-user rate limiting for llm_service endpoints.

Backed by the same Redis instance Celery already uses
(django.conf.settings.CELERY_BROKER_URL) - a different DB index so
rate-limit keys never collide with Celery's own broker data. No new
infrastructure, and redis-py is already an installed dependency (Celery
needs it), so no new package either.

Fixed-window counter via Redis INCR/EXPIRE: simple, atomic, and precise
enough for abuse/cost protection - not a smooth sliding window, and
doesn't need to be one for this.

Per-user, not per-IP, on purpose: this app is used from behind shared
NAT/corporate proxies, where per-IP limiting would unfairly lump unrelated
users together. Matches Django's old per-user ScopedRateThrottle on
/api/chat/ (also 30/min) before that endpoint was retired.
"""

import time

import redis.asyncio as redis
from django.conf import settings
from fastapi import Depends, HTTPException, status

from apps.accounts.models import User
from llm_service.auth import get_current_user

_redis = redis.from_url(settings.CELERY_BROKER_URL, db=1, decode_responses=True)


def rate_limit(scope: str, limit: int, window_seconds: int):
    """Returns a FastAPI dependency enforcing `limit` requests per
    `window_seconds` per user, for the given `scope` (so different
    endpoints don't share a counter unless they're meant to).
    """

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
