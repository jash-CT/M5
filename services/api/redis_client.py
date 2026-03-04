"""Redis client for API (cache, pub/sub for rules engine)."""
import os
from typing import Optional

import redis.asyncio as redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


async def redis_healthy() -> bool:
    try:
        r = await get_redis()
        await r.ping()
        return True
    except Exception:
        return False
