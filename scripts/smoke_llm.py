"""Manual smoke test for the FR-02 LLM client. Run: scripts/smoke_llm.py [--dry-run]"""

from __future__ import annotations

import argparse
import json
import sys

from alokasi_agent.llm import LLMClient, to_openai_tools
from alokasi_agent.schema import CREATE_ALOKASI_TOOL

EXAMPLE_MESSAGE = (
    "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan "
    "Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026"
)


def build_request() -> tuple[list[dict], list[dict]]:
    messages = [{"role": "user", "content": EXAMPLE_MESSAGE}]
    return messages, to_openai_tools(CREATE_ALOKASI_TOOL)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the FR-02 LLM client")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the request payload without calling the API (no key needed)",
    )
    args = parser.parse_args()

    messages, tools = build_request()

    if args.dry_run:
        print(json.dumps({"messages": messages, "tools": tools}, indent=2, ensure_ascii=False))
        return 0

    client = LLMClient()
    response = client.complete(messages, tools=tools)
    message = response.choices[0].message

    if message.tool_calls:
        for call in message.tool_calls:
            print(f"tool call: {call.function.name}")
            print(json.dumps(json.loads(call.function.arguments), indent=2, ensure_ascii=False))
    else:
        print("text reply (no tool call):")
        print(message.content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
