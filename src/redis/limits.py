import math
from datetime import datetime, timezone
from src.redis.client import get_redis
from src.config import settings

DAILY_PREFIX = "daily:"


def _seconds_until_midnight() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if tomorrow <= now:
        tomorrow = tomorrow.replace(day=tomorrow.day + 1)
    return math.ceil((tomorrow - now).total_seconds())


async def check_and_increment(user_id: int) -> tuple[bool, int]:
    r = get_redis()
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


async def get_daily_usage(user_id: int) -> int:
    r = get_redis()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"{DAILY_PREFIX}{user_id}:{today}"
    current = await r.get(key)
    return int(current) if current else 0
