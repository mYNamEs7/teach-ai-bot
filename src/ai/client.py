import json
import asyncio
from typing import AsyncGenerator, List, Dict
import httpx
from src.config import settings
from src.ai.prompts import get_system_prompt

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_MODEL = "openrouter/free"

HEADERS = {
    "Authorization": f"Bearer {settings.openrouter_api_key}",
    "Content-Type": "application/json",
    "HTTP-Referer": "https://t.me/teach_ai_bot",
    "X-Title": "Teach AI Bot",
}


async def stream_ai_response(
    model: str,
    messages: List[Dict[str, str]],
    timeout: int = 60,
) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
            "max_tokens": 2048,
        }
        async with client.stream("POST", OPENROUTER_URL, json=payload, headers=HEADERS) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                raise RuntimeError(f"OpenRouter error {response.status_code}: {error_body.decode()}")
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
                except json.JSONDecodeError:
                    continue


async def get_ai_response(
    model: str,
    messages: List[Dict[str, str]],
    timeout: int = 60,
) -> str:
    full = ""
    async for chunk in stream_ai_response(model, messages, timeout):
        full += chunk
    return full


def build_messages(mode: str, context: List[Dict[str, str]], user_text: str) -> List[Dict[str, str]]:
    system_prompt = get_system_prompt(mode)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(context)
    messages.append({"role": "user", "content": user_text})
    return messages
