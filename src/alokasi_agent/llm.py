"""LLM settings and the one chat-completion call, as plain functions."""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


def load_config() -> dict[str, Any]:
    """Read LLM settings from the environment as a plain dict."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set. Export it before calling complete().")
    return {
        "api_key": api_key,
        "model": os.environ.get("ALOKASI_MODEL") or "gpt-4o-mini",
        "temperature": float(os.environ.get("ALOKASI_TEMPERATURE", 0.0)),
        "timeout": float(os.environ.get("ALOKASI_TIMEOUT", 30.0)),
        "base_url": os.environ.get("OPENAI_BASE_URL") or None,
        "reasoning_effort": os.environ.get("ALOKASI_REASONING_EFFORT", "").strip() or None,
    }


def complete(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One chat completion, returned as a plain dict (OpenAI response object dumped)."""
    config = config or load_config()
    client = OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"],
        timeout=config["timeout"],
    )
    kwargs: dict[str, Any] = {
        "model": config["model"],
        "messages": messages,
        "temperature": config["temperature"],
    }
    if config["reasoning_effort"]:
        kwargs["reasoning_effort"] = config["reasoning_effort"]
    if tools:
        kwargs["tools"] = tools
    return client.chat.completions.create(**kwargs).model_dump()


def to_openai_tools(
    tool: dict[str, Any] | Sequence[dict[str, Any]] #yang baru ada tambahan sequence
) -> list[dict[str, Any]]:
    if isinstance(tool, dict):
        tool_list = [tool]
    else:
        tool_list = tool

    return [
        {
            "type": "function",
            "function": {
                "name": item["name"],
                "description": item["description"],
                "parameters": item["input_schema"],
            },
        }
        for item in tool_list
    ]
