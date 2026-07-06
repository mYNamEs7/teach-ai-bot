import logging
from src.redis.limits import check_and_increment, get_daily_usage
from src.config import settings

log = logging.getLogger(__name__)


async def is_rate_limited(user_id: int, is_premium: bool) -> tuple[bool, int]:
    if is_premium:
        return False, 0
    allowed, count = await check_and_increment(user_id)
    if allowed:
        return False, count
    return True, count


async def get_remaining_requests(user_id: int, is_premium: bool) -> int:
    if is_premium:
        return -1
    used = await get_daily_usage(user_id)
    return max(0, settings.free_daily_limit - used)
