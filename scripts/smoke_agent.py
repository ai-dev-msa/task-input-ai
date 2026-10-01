"""Live done-condition for FR-04 (and FR-07 with --partial).

Run: scripts/smoke_agent.py  (needs OPENAI_API_KEY in .env)
Exit 0 iff run() ends in a create_alokasi tool call whose arguments match
the PRD section 6 sample exactly.

Run: scripts/smoke_agent.py --partial  (FR-07)
Starts from a partial message, prints each clarifying question, and reads
your answers from stdin. Exit 0 iff a complete call (all six fields) comes
back — the date is relative, so there is no fixed sample to compare.
"""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from alokasi_agent import run

EXAMPLE_MESSAGE = (
    "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan "
    "Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026"
)
SAMPLE_ARGUMENTS = {
    "nama_karyawan": "Imam Ihsani",
    "nama_proyek": "OPRS Divisi WIN 2026",
    "tanggal": "2026-09-29",
    "jenis_pekerjaan": "Development Modul PPN",
    "jam_mulai": "09:00",
    "jam_selesai": "12:00",
}
PARTIAL_MESSAGE = "besok aku ngerjain modul PPN jam 1 sampai jam 4"
USER = "Andi Wijaya"
EMPLOYEES = ["Imam Ihsani", "Budi Santoso"]
PROJECTS = ["OPRS Divisi WIN 2026"]
MAX_TURNS = 3
PARTIAL_MAX_TURNS = 6  # clarification + confirmation are extra turns


def ask_user() -> str | None:
    """Read the next answer from stdin; None aborts the run."""
    try:
        answer = input("you: ").strip()
    except EOFError:
        answer = ""
    if not answer:
        print("aborted (no answer)")
        return None
    return answer


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Live check for run()")
    parser.add_argument(
        "--partial",
        action="store_true",
        help="FR-07: start from a partial message and answer the questions interactively",
    )
    args = parser.parse_args()

    history: list | None = None
    message = PARTIAL_MESSAGE if args.partial else EXAMPLE_MESSAGE
    max_turns = PARTIAL_MAX_TURNS if args.partial else MAX_TURNS
    envelope = None
    for turn in range(1, max_turns + 1):
        envelope, history = run(
            message,
            user_name=USER,
            employees=EMPLOYEES,
            projects=PROJECTS,
            history=history,
        )
        print(f"turn {turn}: type={envelope['type']}")
        if envelope["type"] == "function_call":
            break
        print(f"assistant: {envelope['reply']}")
        if args.partial:
            message = ask_user()
            if message is None:
                return 1
        else:
            message = "ya"
    else:
        print(f"no tool call after {max_turns} turns, last reply: {envelope['reply']}")
        return 1

    if envelope["function_name"] != "create_alokasi":
        print(f"unexpected function: {envelope['function_name']}")
        return 1
    arguments = json.loads(envelope["arguments"])
    print(json.dumps(arguments, indent=2, ensure_ascii=False))

    if args.partial:
        missing = [field for field in SAMPLE_ARGUMENTS if not arguments.get(field)]
        if missing:
            print(f"complete call: NO (missing or empty: {missing})")
            return 1
        print("complete call: yes")
        return 0

    if arguments == SAMPLE_ARGUMENTS:
        print("arguments match PRD sample: yes")
        return 0
    print("arguments match PRD sample: NO")
    return 1


if __name__ == "__main__":
    sys.exit(main())
