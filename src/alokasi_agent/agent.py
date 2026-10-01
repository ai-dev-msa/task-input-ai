from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from alokasi_agent.llm import complete as default_complete
from alokasi_agent.llm import to_openai_tools
from alokasi_agent.prompt import build_system_prompt
from alokasi_agent.schema import CREATE_ALOKASI_TOOL, validate_arguments


def _alokasi_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    """Every create_alokasi tool call in the model's reply (FR-08: one per row).

    The tool list only offers create_alokasi, but a stray call to any other
    function is ignored rather than treated as a row.
    """
    calls = message.get("tool_calls") or []
    return [
        tc
        for tc in calls
        if (tc.get("function") or {}).get("name") == "create_alokasi"
    ]


def _validate_calls(calls: list[dict[str, Any]]) -> dict[str, list[str]]:
    """FR-05: validation errors per tool-call id. Empty list = that row is safe."""
    return {
        tc.get("id", ""): validate_arguments(tc["function"].get("arguments", ""))
        for tc in calls
    }


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
    calls = _alokasi_calls(message)
    errors_by_id = _validate_calls(calls)

    if any(errors_by_id.values()):
        # FR-05: retry once, handing the validation errors back to the model.
        # The API needs a tool reply for every tool call in that assistant turn;
        # a row that already validated gets "OK" so its id still has a reply.
        messages = messages + [
            {"role": "assistant", "content": message.get("content"),
             "tool_calls": message.get("tool_calls")},
            *[
                {"role": "tool", "tool_call_id": tc.get("id", ""),
                 "content": "\n".join(errors_by_id.get(tc.get("id", ""), []))
                 or "OK"}
                for tc in message.get("tool_calls") or []
            ],
        ]
        response = complete(messages, tools=tools)
        message = response["choices"][0]["message"]
        calls = _alokasi_calls(message)
        errors_by_id = _validate_calls(calls)

    if any(errors_by_id.values()):
        # Still malformed after the retry: refuse instead of sending a partial call.
        errors = [
            error for tc in calls for error in errors_by_id.get(tc.get("id", ""), [])
        ]
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
    elif calls:
        # One row keeps the model's object string (PRD sample shape unchanged);
        # several rows become a JSON array string the backend iterates (FR-08).
        rows = [tc["function"]["arguments"] for tc in calls]
        arguments = (
            rows[0] if len(rows) == 1 else json.dumps([json.loads(row) for row in rows])
        )
        envelope = {
            "success": True,
            "type": "function_call",
            "function_name": "create_alokasi",
            "arguments": arguments,
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
