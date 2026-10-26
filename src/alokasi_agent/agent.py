from __future__ import annotations

import json
import difflib
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any

from alokasi_agent.llm import complete as default_complete
from alokasi_agent.llm import to_openai_tools
from alokasi_agent.prompt import build_system_prompt, parse_summary
from alokasi_agent.schema import (
    CREATE_ALOKASI_TOOL,
    FIND_EMPLOYEE_TOOL,
    FIND_PROJECT_TOOL,
    OPTIONAL_FIELDS,
    validate_arguments,
)

MAX_ROUNDS = 6


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


def _find_calls(message: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(tool_call id, function name, name) for every find_* call in the reply."""
    found: list[tuple[str, str, str]] = []
    for tc in message.get("tool_calls") or []:
        function = tc.get("function") or {}
        if function.get("name") not in ("find_employee", "find_project"):
            continue
        try:
            raw = json.loads(function.get("arguments") or "")
        except json.JSONDecodeError:
            raw = {}
        value = str(raw.get("name", "")) if isinstance(raw, dict) else ""
        found.append((tc.get("id", ""), function["name"], value.strip()))
    return found


def _validate_calls(calls: list[dict[str, Any]]) -> dict[str, list[str]]:
    """FR-05: validation errors per tool-call id. Empty list = that row is safe."""
    return {
        tc.get("id", ""): validate_arguments(tc["function"].get("arguments", ""))
        for tc in calls
    }


def _canonical_map(valid: Sequence[str]) -> dict[str, str]:
    """casefolded name -> exact list spelling (first spelling wins)."""
    canonical: dict[str, str] = {}
    for name in valid:
        canonical.setdefault(name.strip().casefold(), name)
    return canonical


def _missing_names(values: Sequence[str], valid: Sequence[str]) -> list[str]:
    """Values with no trim+case-insensitive match in `valid` (order kept)."""
    canonical = _canonical_map(valid)
    return [value for value in values if value.strip().casefold() not in canonical]


def _resolve_name(value: str, tool_name: str, valid: Sequence[str]) -> str:
    """Tool result for one find_* call: match text only, never a user question.

    The model decides what to ask the user after reading this (FR-09).
    """
    kind = "project" if tool_name == "find_project" else "employee"
    if not valid:
        return f"The {kind} list is unavailable, try again later."
    if not value:
        return 'Could not read the name. Call again with {"name": "..."} as plain text.'
    canonical = _canonical_map(valid)
    wanted = value.strip().casefold()
    if wanted in canonical:
        return f"Matched: {canonical[wanted]}"
    candidates = difflib.get_close_matches(value, list(canonical.values()), n=3, cutoff=0.5)
    if candidates:
        return (
            f'No exact match for "{value}". Closest: {", ".join(candidates)}. '
            "Ask the user which one is meant."
        )
    return f'"{value}" not found in the {kind} list. Ask the user to check the spelling.'


def _redirect_problems(
    calls: list[dict[str, Any]], employees: Sequence[str], projects: Sequence[str]
) -> dict[str, str]:
    """Per call id: the tool error that sends unresolved names back to find_*.

    Empty string for a call whose names are all in the lists. Runs only after
    FR-05 passed, so the arguments parse as a JSON object here.
    """
    problems: dict[str, str] = {}
    for tc in calls:
        args = json.loads(tc["function"].get("arguments", ""))
        lines: list[str] = []
        for value in _missing_names([str(args.get("nama_karyawan", ""))], employees):
            lines.append(
                f'Karyawan "{value}" belum dipastikan. Panggil find_employee '
                "untuk menyelesaikannya, lalu kirim ulang create_alokasi."
            )
        for value in _missing_names([str(args.get("nama_proyek", ""))], projects):
            lines.append(
                f'Proyek "{value}" belum dipastikan. Panggil find_project '
                "untuk menyelesaikannya, lalu kirim ulang create_alokasi."
            )
        tim = str(args.get("tim_pekerjaan") or "")
        members = [part.strip() for part in tim.split(",") if part.strip()]
        for value in _missing_names(members, employees):
            lines.append(
                f'Anggota tim "{value}" belum dipastikan. Panggil find_employee '
                "untuk menyelesaikannya, atau minta user menghapusnya dari tim."
            )
        problems[tc.get("id", "")] = " ".join(lines)
    return problems


def _missing_lists_message(
    employees: Sequence[str], projects: Sequence[str]
) -> str | None:
    """Fail-closed: an empty list means the names cannot be checked at all
    (the server fetch may have failed), so a call must not reach the ERP."""
    if employees and projects:
        return None
    if not employees and not projects:
        return "Daftar karyawan dan proyek tidak tersedia, coba lagi."
    if not employees:
        return "Daftar karyawan tidak tersedia, coba lagi."
    return "Daftar proyek tidak tersedia, coba lagi."


def _canonical_name(value: str, valid: Sequence[str]) -> str:
    """Exact list spelling for `value`, or `value` itself when nothing fits."""
    wanted = value.strip().casefold()
    for name in valid:
        if name.strip().casefold() == wanted:
            return name
    return value


def _canonicalize_row(
    raw: str, employees: Sequence[str], projects: Sequence[str]
) -> str:
    """Rewrite a checked row's names to the exact list spellings.

    Returns `raw` untouched when nothing changed, so an already-canonical
    row keeps the model's exact JSON string (PRD sample shape unchanged).
    """
    args = json.loads(raw)
    changed = False
    # Explicit null means "user did not provide it"; the backend contract is
    # an absent key, so drop those and emit the stripped JSON.
    for name in OPTIONAL_FIELDS:
        value = args.get(name)
        if name in args and (
            value is None or (isinstance(value, str) and not value.strip())
    ):
            del args[name]
            changed = True
    for field, valid in (("nama_karyawan", employees), ("nama_proyek", projects)):
        value = str(args.get(field, ""))
        canonical = _canonical_name(value, valid)
        if canonical != value:
            args[field] = canonical
            changed = True
    tim = args.get("tim_pekerjaan")
    if isinstance(tim, str) and tim.strip():
        members = [part.strip() for part in tim.split(",") if part.strip()]
        joined = ", ".join(_canonical_name(member, employees) for member in members)
        if joined != tim:
            args["tim_pekerjaan"] = joined
            changed = True
    return raw if not changed else json.dumps(args, separators=(",", ":"))


def _confirmed_rows(history: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """Structured rows from the pending confirmation summary, or [].

    The last assistant turn is the summary the user is confirming; prompt's
    parse_summary turns its 'a | b | c | d | e' lines back into row dicts.
    [] means "nothing to compare against" (no summary, or one that will not
    parse), which turns the row guard off and keeps the old behaviour.
    """
    for turn in reversed(history):
        if turn.get("role") == "assistant":
            return parse_summary(turn.get("content"))
    return []


def _same_rows(calls: list[dict[str, Any]], confirmed: list[dict[str, str]]) -> bool:
    """True when the model's calls are exactly the confirmed rows (any order).

    Null values count as absent: a call sending "review": null matches a
    confirmation row without the key.
    FR-05 already rejected null on required fields, so dropping None for
    any key here only ever hits optionals.
    """

    def canonical(rows):
        cleaned = [
            {k: v for k, v in row.items() if v is not None}
            for row in rows
        ]
        return sorted(
            json.dumps(row, sort_keys=True, ensure_ascii=False) for row in cleaned
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

    Bounded round loop: find_* calls get match results, create_alokasi calls
    get FR-05 validation, one row-guard nudge, and up to 2 redirects back to
    find_* for unresolved names. MAX_ROUNDS total, refusal when exhausted.
    """
    complete = complete or default_complete
    system = build_system_prompt(now or datetime.now(timezone.utc), user_name)
    prior = list(history or [])
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        *prior,
        {"role": "user", "content": raw_message},
    ]
    tools = to_openai_tools(CREATE_ALOKASI_TOOL, FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL)
    confirmed = _confirmed_rows(prior)

    validation_retries = 0
    redirects = 0
    nudged = False
    refuse_reason = ""
    message: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []

    for _ in range(MAX_ROUNDS):
        response = complete(messages, tools=tools)
        message = response["choices"][0]["message"]

        finds = _find_calls(message)
        if finds:
            # Every tool call id in this turn gets a reply: find_* carries the
            # match result, a create_alokasi riding along gets "OK" and is only
            # acted on if the model sends it again in a later round.
            results = {
                fid: _resolve_name(
                    name, tool, employees if tool == "find_employee" else projects
                )
                for fid, tool, name in finds
            }
            messages = messages + [
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": message.get("tool_calls"),
                },
                *[
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": results.get(tc.get("id", ""), "OK"),
                    }
                    for tc in message.get("tool_calls") or []
                ],
            ]
            continue

        calls = _alokasi_calls(message)
        errors_by_id = _validate_calls(calls)

        if any(errors_by_id.values()):
            # FR-05: retry once, handing the validation errors back to the model.
            if validation_retries >= 1:
                errors = [
                    error
                    for tc in calls
                    for error in errors_by_id.get(tc.get("id", ""), [])
                ]
                refuse_reason = (
                    "Data tidak valid setelah dicoba ulang: " + "; ".join(errors)
                )
                break
            validation_retries += 1
            messages = messages + [
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": message.get("tool_calls"),
                },
                *[
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": "\n".join(errors_by_id.get(tc.get("id", ""), []))
                        or "OK",
                    }
                    for tc in message.get("tool_calls") or []
                ],
            ]
            continue

        if not calls:
            break  # plain text reply (or only unknown tool names) -> text envelope

        if missing := _missing_lists_message(employees, projects):
            # Fail-closed: with no list to check against, nothing reaches the ERP.
            refuse_reason = missing
            break

        if confirmed and not _same_rows(calls, confirmed):
            # FR-08 row guard: nudge once with the confirmed rows, refuse after.
            if nudged:
                refuse_reason = (
                    f"Isi alokasi tidak sesuai konfirmasi ({len(calls)} panggilan vs "
                    f"{len(confirmed)} baris, atau nilainya berbeda). "
                    "Tidak ada data yang dikirim."
                )
                break
            nudged = True
            messages = messages + [
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": message.get("tool_calls"),
                },
                *[
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": "OK",
                    }
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
            continue

        problems = _redirect_problems(calls, employees, projects)
        if any(problems.values()):
            # Fail closed: unresolved names go back to the model as a redirect
            # to find_* instead of a user-facing question (max 2 rounds).
            if redirects >= 2:
                refuse_reason = (
                    "Nama belum dapat dipastikan setelah beberapa percobaan. "
                    "Tidak ada data yang dikirim."
                )
                break
            redirects += 1
            messages = messages + [
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": message.get("tool_calls"),
                },
                *[
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "content": problems.get(tc.get("id", ""), "") or "OK",
                    }
                    for tc in message.get("tool_calls") or []
                ],
            ]
            continue

        # Accept: one row keeps the model's object string (PRD sample shape
        # unchanged); several rows become a JSON array string (FR-08). Names
        # are rewritten to the exact list spellings first.
        rows = [
            _canonicalize_row(tc["function"]["arguments"], employees, projects)
            for tc in calls
        ]
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
        new_history = [
            *prior,
            {"role": "user", "content": raw_message},
            {"role": "assistant", "content": history_content},
        ]
        envelope["history"] = new_history
        return envelope, new_history
    else:
        # Loop used up MAX_ROUNDS without a decision (e.g. the model keeps
        # calling find_* without ever emitting create_alokasi).
        if not refuse_reason:
            refuse_reason = (
                "Percobaan terlalu banyak tanpa hasil. Tidak ada data yang dikirim."
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
