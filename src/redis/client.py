import redis.asyncio as redis
from src.config import settings

redis_client: redis.Redis | None = None


async def init_redis() -> redis.Redis:
    global redis_client
    redis_client = await redis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None


def get_redis() -> redis.Redis:
    if redis_client is None:
        raise RuntimeError("Redis not initialized")
    return redis_client
