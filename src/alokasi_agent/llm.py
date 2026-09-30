from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletion


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    timeout: float = 30.0
    base_url: str | None = None

    @classmethod
    def from_env(cls) -> LLMConfig:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Export it before creating an LLMClient."
            )
        return cls(
            api_key=api_key,
            model=os.environ.get("ALOKASI_MODEL", cls.model),
            temperature=_env_float("ALOKASI_TEMPERATURE", cls.temperature),
            timeout=_env_float("ALOKASI_TIMEOUT", cls.timeout),
            base_url=os.environ.get("OPENAI_BASE_URL") or None,
        )


class LLMClient:
    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self._client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatCompletion:
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
        }
        if tools:
            kwargs["tools"] = tools
        return self._client.chat.completions.create(**kwargs)


def to_openai_tools(tool: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
    ]
