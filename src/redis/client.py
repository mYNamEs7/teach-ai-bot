import logging
import redis.asyncio as redis
from src.config import settings

log = logging.getLogger(__name__)

redis_client: redis.Redis | None = None


async def init_redis() -> redis.Redis:
    global redis_client
    try:
        redis_client = await redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
            socket_keepalive=True,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
        await redis_client.ping()
        log.info("Redis connected")
    except Exception as e:
        log.warning("Redis connection failed: %s", e)
        redis_client = None
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client:
        try:
            await redis_client.close()
        except Exception:
            pass
        redis_client = None


async def ensure_redis() -> redis.Redis:
    global redis_client
    if redis_client is None:
        await init_redis()
    if redis_client is None:
        raise RuntimeError("Redis not available")
    return redis_client


def get_redis() -> redis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis not initialized")
    return redis_client
