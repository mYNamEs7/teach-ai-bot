import math
import logging
from datetime import datetime, timezone
from src.redis.client import ensure_redis
from src.config import settings

log = logging.getLogger(__name__)
DAILY_PREFIX = "daily:"


def _seconds_until_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if tomorrow <= now:
        tomorrow = tomorrow.replace(day=tomorrow.day + 1)
    return math.ceil((tomorrow - now).total_seconds())


async def check_and_increment(user_id: int) -> tuple[bool, int]:
    try:
        r = await ensure_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{DAILY_PREFIX}{user_id}:{today}"
        current = await r.get(key)
        if current is None:
            ttl = _seconds_until_midnight()
            await r.setex(key, ttl, 1)
            return True, 1
        count = int(current)
        if count >= settings.free_daily_limit:
            return False, count
        await r.incr(key)
        return True, count + 1
    except Exception as e:
        log.warning("Redis rate limit failed (allowing request): %s", e)
        return True, 0


async def get_daily_usage(user_id: int) -> int:
    try:
        r = await ensure_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{DAILY_PREFIX}{user_id}:{today}"
        current = await r.get(key)
        return int(current) if current else 0
    except Exception as e:
        log.warning("Redis get_daily_usage failed: %s", e)
        return -1
