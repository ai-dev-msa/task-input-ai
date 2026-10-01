"""Manual smoke test for the FR-02 LLM client and system prompt.

Run: scripts/smoke_llm.py [--dry-run] [--user NAME] [--employees-file F] [--projects-file F]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from alokasi_agent.llm import LLMClient, to_openai_tools
from alokasi_agent.prompt import build_system_prompt
from alokasi_agent.schema import CREATE_ALOKASI_TOOL

EXAMPLE_MESSAGE = (
    "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan "
    "Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026"
)

DEFAULT_USER = "Andi Wijaya"
DEFAULT_EMPLOYEES = ["Imam Ihsani", "Budi Santoso"]
DEFAULT_PROJECTS = ["OPRS Divisi WIN 2026"]
MAX_TURNS = 10


def load_names(
    path: str | None,
    default: list[str],
    label: str,
    parser: argparse.ArgumentParser,
) -> list[str]:
    if path is None:
        return default
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"{label} file is not readable JSON: {exc}")
    if not isinstance(data, list) or not all(isinstance(item, str) and item for item in data):
        parser.error(f"{label} file must be a JSON array of non-empty strings")
    return data


def build_request(
    user: str,
    employees: list[str],
    projects: list[str],
) -> tuple[list[dict], list[dict]]:
    system = build_system_prompt(datetime.now(timezone.utc), user, employees, projects)
    messages: list[dict] = [
        {"role": "system", "content": system},
        {"role": "user", "content": EXAMPLE_MESSAGE},
    ]
    return messages, to_openai_tools(CREATE_ALOKASI_TOOL)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the FR-02 LLM client")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the request payload without calling the API (no key needed)",
    )
    parser.add_argument(
        "--user",
        default=DEFAULT_USER,
        help="logged-in user injected into the system prompt",
    )
    parser.add_argument(
        "--employees-file",
        help="JSON file with an array of valid employee names",
    )
    parser.add_argument(
        "--projects-file",
        help="JSON file with an array of valid project names",
    )
    args = parser.parse_args()

    employees = load_names(args.employees_file, DEFAULT_EMPLOYEES, "employees", parser)
    projects = load_names(args.projects_file, DEFAULT_PROJECTS, "projects", parser)
    messages, tools = build_request(args.user, employees, projects)

    if args.dry_run:
        print(json.dumps({"messages": messages, "tools": tools}, indent=2, ensure_ascii=False))
        return 0

    client = LLMClient()
    for _ in range(MAX_TURNS):
        response = client.complete(messages, tools=tools)
        message = response.choices[0].message
        if message.tool_calls:
            for call in message.tool_calls:
                print(f"tool call: {call.function.name}")
                print(json.dumps(json.loads(call.function.arguments), indent=2, ensure_ascii=False))
            return 0
        print("assistant:", message.content or "")
        messages.append({"role": "assistant", "content": message.content or ""})
        while True:
            try:
                reply = input("you: ").strip()
            except EOFError:
                return 0
            if reply.lower() in {"q", "quit", "exit"}:
                return 0
            if reply:
                break
        messages.append({"role": "user", "content": reply})
    print("max turns reached without a tool call")
    return 1


if __name__ == "__main__":
    sys.exit(main())
