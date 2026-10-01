"""Live done-condition for FR-04: run() over the FRD example message.

Run: scripts/smoke_agent.py  (needs OPENAI_API_KEY in .env)
Exit 0 iff run() ends in a create_alokasi tool call whose arguments match
the PRD section 6 sample exactly.
"""

from __future__ import annotations

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
USER = "Andi Wijaya"
EMPLOYEES = ["Imam Ihsani", "Budi Santoso"]
PROJECTS = ["OPRS Divisi WIN 2026"]
MAX_TURNS = 3


def main() -> int:
    load_dotenv()
    history: list | None = None
    message = EXAMPLE_MESSAGE
    envelope = None
    for turn in range(1, MAX_TURNS + 1):
        envelope, history = run(
            message,
            user_name=USER,
            employees=EMPLOYEES,
            projects=PROJECTS,
            history=history,
        )
        print(f"turn {turn}: type={envelope.type}")
        if envelope.type == "function_call":
            break
        print(f"assistant: {envelope.reply}")
        message = "ya"
    else:
        print(f"no tool call after {MAX_TURNS} turns, last reply: {envelope.reply}")
        return 1

    if envelope.function_name != "create_alokasi":
        print(f"unexpected function: {envelope.function_name}")
        return 1
    arguments = json.loads(envelope.arguments)
    print(json.dumps(arguments, indent=2, ensure_ascii=False))
    if arguments == SAMPLE_ARGUMENTS:
        print("arguments match PRD sample: yes")
        return 0
    print("arguments match PRD sample: NO")
    return 1


if __name__ == "__main__":
    sys.exit(main())
