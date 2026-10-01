from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from alokasi_agent.llm import complete as default_complete
from alokasi_agent.llm import to_openai_tools
from alokasi_agent.prompt import build_system_prompt
from alokasi_agent.schema import CREATE_ALOKASI_TOOL, validate_arguments


def _first_tool_call(message: dict[str, Any]) -> dict[str, Any] | None:
    tool_calls = message.get("tool_calls") or []
    return tool_calls[0] if tool_calls else None


def run(
    raw_message: str,
    *,
    user_name: str,
    employees: Sequence[str],
    projects: Sequence[str],
    history: list[dict[str, Any]] | None = None,
    user_id: str | None = None,
    now: datetime | None = None,
    complete: Any = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Send one user message to the LLM and return (envelope dict, new history).

    `complete` is an injectable function `(messages, tools) -> dict` so tests
    can pass a stub; by default it is llm.complete.
    """
    complete = complete or default_complete
    system = build_system_prompt(
        now or datetime.now(timezone.utc), user_name, employees, projects
    )
    prior = list(history or [])
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        *prior,
        {"role": "user", "content": raw_message},
    ]
    tools = to_openai_tools(CREATE_ALOKASI_TOOL)

    response = complete(messages, tools=tools)
    message = response["choices"][0]["message"]
    call = _first_tool_call(message)
    errors = validate_arguments(call["function"].get("arguments", "")) if call else []

    if errors:
        # FR-05: retry once, handing the validation errors back to the model.
        # The API needs a tool reply for every tool call in that assistant turn.
        messages = messages + [
            {"role": "assistant", "content": message.get("content"),
             "tool_calls": message.get("tool_calls")},
            *[
                {"role": "tool", "tool_call_id": tc.get("id", ""),
                 "content": "\n".join(errors)}
                for tc in message.get("tool_calls") or []
            ],
        ]
        response = complete(messages, tools=tools)
        message = response["choices"][0]["message"]
        call = _first_tool_call(message)
        errors = validate_arguments(call["function"].get("arguments", "")) if call else []

    if errors:
        # Still malformed after the retry: refuse instead of sending a partial call.
        reason = "Data tidak valid setelah dicoba ulang: " + "; ".join(errors)
        envelope = {
            "success": False,
            "type": "error",
            "function_name": "",
            "arguments": "",
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": reason,
        }
        history_content: str = reason
    elif call is not None:
        envelope = {
            "success": True,
            "type": "function_call",
            "function_name": call["function"]["name"],
            "arguments": call["function"]["arguments"],
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": message.get("content"),
        }
        history_content = message.get("content") or ""
    else:
        envelope = {
            "success": True,
            "type": "text",
            "function_name": "",
            "arguments": "",
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": message.get("content"),
        }
        history_content = message.get("content") or ""

    new_history = [
        *prior,
        {"role": "user", "content": raw_message},
        {"role": "assistant", "content": history_content},
    ]
    return envelope, new_history
