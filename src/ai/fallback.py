import json
import asyncio
import logging
from typing import List, Optional
import httpx
from src.config import settings
from src.redis.client import ensure_redis

log = logging.getLogger(__name__)

FALLBACK_CACHE_KEY = "available_free_models"
FALLBACK_LOCK_KEY = "fallback_lock"
FALLBACK_CACHE_TTL = 21600

_fallback_lock = asyncio.Lock()

FREE_MODELS_FILE = "free_models.json"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

CUSTOM_FREE_MODELS: List[str] = []


def set_custom_free_models(models: List[str]) -> None:
    global CUSTOM_FREE_MODELS
    CUSTOM_FREE_MODELS = models


async def _probe_free_models() -> List[str]:
    try:
        headers = {
            "User-Agent": "TeachAIBot/1.0",
            "Authorization": f"Bearer {settings.openrouter_api_key}",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(OPENROUTER_MODELS_URL, headers=headers)
            if resp.status_code != 200:
                log.warning("Failed to fetch models from OpenRouter: %d", resp.status_code)
                return []
            data = resp.json()
            models = []
            for model in data.get("data", []):
                pricing = model.get("pricing", {})
                prompt_price = pricing.get("prompt", 1)
                try:
                    is_free = float(prompt_price) == 0.0
                except (TypeError, ValueError):
                    is_free = str(prompt_price) in ("0", "free", "0.0")
                if is_free:
                    models.append(model["id"])
            return models
    except Exception as e:
        log.error("Error probing free models: %s", e)
        return []


async def get_available_models() -> List[str]:
    try:
        r = await ensure_redis()
    except RuntimeError:
        return CUSTOM_FREE_MODELS or ["openrouter/free"]
    cached = await r.get(FALLBACK_CACHE_KEY)
    models = []
    if cached:
        try:
            models = json.loads(cached)
        except (json.JSONDecodeError, TypeError):
            pass

    merged_ids = set(models) | set(CUSTOM_FREE_MODELS)
    return list(merged_ids) if merged_ids else ["openrouter/free"]


async def update_available_models() -> List[str]:
    async with _fallback_lock:
        existing = []
        try:
            r = await ensure_redis()
            existing_raw = await r.get(FALLBACK_CACHE_KEY)
            if existing_raw:
                try:
                    existing = json.loads(existing_raw)
                except (json.JSONDecodeError, TypeError):
                    existing = []
        except RuntimeError:
            pass

        fresh = await _probe_free_models()
        merged = list(set(existing) | set(fresh) | set(CUSTOM_FREE_MODELS))
        if not merged:
            merged = ["openrouter/free"]
        try:
            r = await ensure_redis()
            await r.setex(FALLBACK_CACHE_KEY, FALLBACK_CACHE_TTL, json.dumps(merged))
        except RuntimeError:
            pass
        log.info("Updated free models: %d available", len(merged))
        return merged


async def get_next_fallback_model(failed_model: str) -> Optional[str]:
    models = await get_available_models()
    for m in models:
        if m != failed_model:
            return m
    return None
