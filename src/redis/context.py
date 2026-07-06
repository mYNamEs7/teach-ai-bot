import json
from typing import List, Dict
from src.redis.client import get_redis
from src.config import settings

CONTEXT_PREFIX = "ctx:"


async def add_message(user_id: int, role: str, content: str) -> None:
    r = get_redis()
    key = f"{CONTEXT_PREFIX}{user_id}"
    message = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    await r.lpush(key, message)
    await r.ltrim(key, 0, settings.redis_context_max - 1)


async def get_context(user_id: int) -> List[Dict[str, str]]:
    r = get_redis()
    key = f"{CONTEXT_PREFIX}{user_id}"
    raw = await r.lrange(key, 0, settings.redis_context_max - 1)
    messages = []
    for item in reversed(raw):
        try:
            messages.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return messages


async def clear_context(user_id: int) -> None:
    r = get_redis()
    key = f"{CONTEXT_PREFIX}{user_id}"
    await r.delete(key)


async def cleanup_old_contexts(days: int = 30) -> int:
    r = get_redis()
    keys = await r.keys(f"{CONTEXT_PREFIX}*")
    removed = 0
    for key in keys:
        ttl = await r.ttl(key)
        if ttl == -2:
            removed += 1
    return removed
