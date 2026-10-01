from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from alokasi_agent.llm import LLMClient, to_openai_tools
from alokasi_agent.prompt import build_system_prompt
from alokasi_agent.schema import CREATE_ALOKASI_TOOL, ResponseEnvelope


def run(
    raw_message: str,
    *,
    user_name: str,
    employees: Sequence[str],
    projects: Sequence[str],
    history: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
    now: datetime | None = None,
    client: LLMClient | None = None,
) -> tuple[ResponseEnvelope, list[dict[str, Any]]]:
    system = build_system_prompt(
        now or datetime.now(timezone.utc), user_name, employees, projects
    )
    prior = list(history or [])
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        *prior,
        {"role": "user", "content": raw_message},
    ]
    response = (client or LLMClient()).complete(
        messages, tools=to_openai_tools(CREATE_ALOKASI_TOOL)
    )
    message = response.choices[0].message

    if message.tool_calls:
        call = message.tool_calls[0]
        envelope = ResponseEnvelope(
            success=True,
            type="function_call",
            function_name=call.function.name,
            arguments=call.function.arguments,
            raw_message=raw_message,
            user_id=user_id,
            reply=message.content,
        )
    else:
        envelope = ResponseEnvelope(
            success=True,
            type="text",
            function_name="",
            arguments="",
            raw_message=raw_message,
            user_id=user_id,
            reply=message.content,
        )

    new_history = [
        *prior,
        {"role": "user", "content": raw_message},
        {"role": "assistant", "content": message.content or ""},
    ]
    return envelope, new_history
