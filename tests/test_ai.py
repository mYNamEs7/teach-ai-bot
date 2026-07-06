import pytest
from src.ai.prompts import get_system_prompt
from src.ai.client import build_messages


def test_get_system_prompt():
    prompt = get_system_prompt("programming")
    assert "программирования" in prompt

    prompt = get_system_prompt("languages")
    assert "иностранных языков" in prompt

    prompt = get_system_prompt("free")
    assert prompt != ""

    prompt = get_system_prompt("unknown")
    assert prompt != ""


def test_build_messages():
    context = [
        {"role": "user", "content": "Привет"},
        {"role": "assistant", "content": "Здравствуй!"},
    ]
    messages = build_messages("programming", context, "Как сделать цикл в Python?")
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"] == "Как сделать цикл в Python?"
