import json
import logging
from typing import List, Dict
from src.redis.client import ensure_redis
from src.config import settings

log = logging.getLogger(__name__)
CONTEXT_PREFIX = "ctx:"


async def add_message(user_id: int, role: str, content: str) -> None:
    try:
        r = await ensure_redis()
        key = f"{CONTEXT_PREFIX}{user_id}"
        message = json.dumps({"role": role, "content": content}, ensure_ascii=False)
        await r.lpush(key, message)
        await r.ltrim(key, 0, settings.redis_context_max - 1)
    except Exception as e:
        log.warning("Redis add_message failed: %s", e)


async def get_context(user_id: int) -> List[Dict[str, str]]:
    try:
        r = await ensure_redis()
        key = f"{CONTEXT_PREFIX}{user_id}"
        raw = await r.lrange(key, 0, settings.redis_context_max - 1)
        messages = []
        for item in reversed(raw):
            try:
                messages.append(json.loads(item))
            except json.JSONDecodeError:
                continue
        return messages
    except Exception as e:
        log.warning("Redis get_context failed: %s", e)
        return []


async def clear_context(user_id: int) -> None:
    try:
        r = await ensure_redis()
        key = f"{CONTEXT_PREFIX}{user_id}"
        await r.delete(key)
    except Exception as e:
        log.warning("Redis clear_context failed: %s", e)


async def cleanup_old_contexts(days: int = 30) -> int:
    try:
        r = await ensure_redis()
        keys = await r.keys(f"{CONTEXT_PREFIX}*")
        removed = 0
        for key in keys:
            ttl = await r.ttl(key)
            if ttl == -2:
                removed += 1
        return removed
    except Exception as e:
        log.warning("Redis cleanup failed: %s", e)
        return 0
