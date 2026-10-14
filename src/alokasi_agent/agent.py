from __future__ import annotations

import json
import difflib
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from alokasi_agent.eval import parse_summary
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


def _project_problem(
    calls: list[dict[str, Any]], projects: Sequence[str]
) -> str | None:
    """Hard list check: every row's nama_proyek must exist in `projects`.

    Trim + case-insensitive match. Returns the user-facing question when some
    row's project is unknown, else None. Empty list means "no list to check
    against", so the check is skipped.
    """
    if not projects:
        return None
    canonical: dict[str, str] = {}
    for name in projects:
        canonical.setdefault(name.strip().casefold(), name)
    lines: list[str] = []
    for tc in calls:
        args = json.loads(tc["function"].get("arguments", ""))
        value = str(args.get("nama_proyek", "")).strip()
        if value.casefold() in canonical:
            continue
        candidates = difflib.get_close_matches(
            value, list(canonical.values()), n=3, cutoff=0.5
        )
        if len(candidates) == 1:
            lines.append(f'Maksud kamu "{candidates[0]}"?')
        elif candidates:
            lines.append(
                f'Proyek "{value}" tidak ada. Pilih: {", ".join(candidates)}'
            )
        else:
            lines.append(f'Proyek "{value}" tidak ada di daftar proyek.')
    return " ".join(lines) or None


def _employee_problem(
    calls: list[dict[str, Any]], employees: Sequence[str]
) -> str | None:
    """Hard list check: every row's nama_karyawan must exist in `employees`.

    Trim + case-insensitive match. Returns the user-facing question when some
    row's employee is unknown, else None. Empty list means "no list to check
    against", so the check is skipped.
    """
    if not employees:
        return None
    canonical: dict[str, str] = {}
    for name in employees:
        canonical.setdefault(name.strip().casefold(), name)
    lines: list[str] = []
    for tc in calls:
        args = json.loads(tc["function"].get("arguments", ""))
        value = str(args.get("nama_karyawan", "")).strip()
        if value.casefold() in canonical:
            continue
        candidates = difflib.get_close_matches(
            value, list(canonical.values()), n=3, cutoff=0.5
        )
        if len(candidates) == 1:
            lines.append(f'Maksud kamu "{candidates[0]}"?')
        elif candidates:
            lines.append(
                f'Karyawan "{value}" tidak ada. Pilih: {", ".join(candidates)}'
            )
        else:
            lines.append(f'Karyawan "{value}" tidak ada di daftar karyawan.')
    return " ".join(lines) or None


def _confirmed_rows(history: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """Structured rows from the pending confirmation summary, or [].

    The last assistant turn is the summary the user is confirming; eval's
    parse_summary turns its 'a | b | c | d | e' lines back into row dicts.
    [] means "nothing to compare against" (no summary, or one that will not
    parse), which turns the row guard off and keeps the old behaviour.
    """
    for turn in reversed(history):
        if turn.get("role") == "assistant":
            return parse_summary(turn.get("content"))
    return []


def _same_rows(calls: list[dict[str, Any]], confirmed: list[dict[str, str]]) -> bool:
    """True when the model's calls are exactly the confirmed rows (any order)."""

    def canonical(rows):
        return sorted(
            json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows
        )

    emitted = [json.loads(tc["function"].get("arguments", "")) for tc in calls]
    return canonical(emitted) == canonical(confirmed)


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

    confirmed = _confirmed_rows(prior)
    refuse_reason = ""
    if any(errors_by_id.values()):
        # Still malformed after the retry: refuse instead of sending a partial call.
        errors = [
            error for tc in calls for error in errors_by_id.get(tc.get("id", ""), [])
        ]
        refuse_reason = "Data tidak valid setelah dicoba ulang: " + "; ".join(errors)
    elif calls and confirmed and not _same_rows(calls, confirmed):
        # FR-08 row guard: the summary above IS what the user confirmed, so
        # the calls must match it exactly — count and every field. Nudge once
        # with the confirmed rows; if they still differ, refuse rather than
        # write rows the user never saw.
        messages = messages + [
            {
                "role": "assistant",
                "content": message.get("content"),
                "tool_calls": message.get("tool_calls"),
            },
            *[
                {"role": "tool", "tool_call_id": tc.get("id", ""), "content": "OK"}
                for tc in message.get("tool_calls") or []
            ],
            {
                "role": "user",
                "content": (
                    f"Konfirmasi tadi menampilkan {len(confirmed)} baris dengan "
                    f"isi berikut:\n"
                    f"{json.dumps(confirmed, ensure_ascii=False)}\n"
                    f"Tapi kamu mengirim {len(calls)} panggilan atau nilainya "
                    f"berbeda. Kirim ulang tepat {len(confirmed)} panggilan "
                    "create_alokasi, satu per baris, persis seperti di atas."
                ),
            },
        ]
        response = complete(messages, tools=tools)
        message = response["choices"][0]["message"]
        calls = _alokasi_calls(message)
        errors_by_id = _validate_calls(calls)
        # Short-circuit: with any error present the calls do not all parse,
        # so _same_rows must not run.
        if any(errors_by_id.values()) or not _same_rows(calls, confirmed):
            refuse_reason = (
                f"Isi alokasi tidak sesuai konfirmasi ({len(calls)} panggilan vs "
                f"{len(confirmed)} baris, atau nilainya berbeda). "
                "Tidak ada data yang dikirim."
            )

    if refuse_reason:
        envelope = {
            "success": False,
            "type": "error",
            "function_name": "",
            "arguments": "",
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": refuse_reason,
        }
        history_content = refuse_reason
    elif calls and (employee_question := _employee_problem(calls, employees)):
        # List miss: ask instead of writing (never a function_call).
        envelope = {
            "success": True,
            "type": "text",
            "function_name": "",
            "arguments": "",
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": employee_question,
        }
        history_content = employee_question
    elif calls and (project_question := _project_problem(calls, projects)):
        # List miss: ask instead of writing (never a function_call).
        envelope = {
            "success": True,
            "type": "text",
            "function_name": "",
            "arguments": "",
            "raw_message": raw_message,
            "user_id": user_id,
            "reply": project_question,
        }
        history_content = project_question
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
    # FR-16: the backend only sees the envelope, so the notepad rides along
    # in it; it stores the list and passes it back as history= next request.
    envelope["history"] = new_history
    return envelope, new_history
