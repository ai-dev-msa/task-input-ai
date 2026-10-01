"""create_alokasi tool contract (FR-01) and argument validation (FR-05).

Plain dicts only. The hand-written input_schema below must stay byte-identical
to tests/golden/create_alokasi_input_schema.json (checked by a test).
"""

import json
import re
from datetime import date
from typing import Any

REQUIRED_FIELDS = (
    "nama_karyawan",
    "nama_proyek",
    "tanggal",
    "jenis_pekerjaan",
    "jam_mulai",
    "jam_selesai",
)

# Optional fields the model may add; absent means "user did not provide".
OPTIONAL_FIELDS = (
    "review",
    "tim_pekerjaan",
)

CREATE_ALOKASI_DESCRIPTION = (
    "Buat satu baris alokasi kerja karyawan untuk satu tanggal: "
    "nama karyawan, nama proyek, tanggal, jenis pekerjaan, dan jam mulai/selesai."
)

CREATE_ALOKASI_TOOL = {
    "name": "create_alokasi",
    "description": CREATE_ALOKASI_DESCRIPTION,
    "input_schema": {
        "additionalProperties": False,
        "properties": {
            "jam_mulai": {
                "description": "Jam mulai dalam format HH:MM, contoh: 09:00",
                "pattern": "^\\d{2}:\\d{2}$",
                "title": "Jam Mulai",
                "type": "string",
            },
            "jam_selesai": {
                "description": "Jam selesai dalam format HH:MM, contoh: 12:00",
                "pattern": "^\\d{2}:\\d{2}$",
                "title": "Jam Selesai",
                "type": "string",
            },
            "jenis_pekerjaan": {
                "description": "Uraian pekerjaan, contoh: Development Modul PPN",
                "minLength": 1,
                "title": "Jenis Pekerjaan",
                "type": "string",
            },
            "nama_karyawan": {
                "description": "Nama lengkap karyawan, contoh: Imam Ihsani",
                "minLength": 1,
                "title": "Nama Karyawan",
                "type": "string",
            },
            "nama_proyek": {
                "description": "Nama proyek, contoh: OPRS Divisi WIN 2026",
                "minLength": 1,
                "title": "Nama Proyek",
                "type": "string",
            },
            "review": {
                "description": "Status/hasil pekerjaan, contoh: [1/1/1/0] Done",
                "minLength": 1,
                "title": "Review",
                "type": "string",
            },
            "tanggal": {
                "description": "Tanggal pekerjaan dalam format YYYY-MM-DD, contoh: 2026-09-29",
                "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                "title": "Tanggal",
                "type": "string",
            },
            "tim_pekerjaan": {
                "description": "Nama anggota tim, dipisah koma, contoh: Bimo Aditya Pangestu, Janie Natalie",
                "minLength": 1,
                "title": "Tim Pekerjaan",
                "type": "string",
            },
        },
        "required": list(REQUIRED_FIELDS),
        "title": "CreateAlokasiArgs",
        "type": "object",
    },
}


def _is_real_date(value: str) -> bool:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _is_valid_time(value: str) -> bool:
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        return False
    # Shape is HH:MM, so hour is [0:2] and minute is [3:5].
    return int(value[:2]) <= 23 and int(value[3:]) <= 59


def _minutes(value: str) -> int:
    return int(value[:2]) * 60 + int(value[3:])


def validate_arguments(arguments: str) -> list[str]:
    """FR-05: return every problem with the model's tool arguments.

    Empty list means the arguments are safe to hand to the backend.
    Error strings are Indonesian because a copy reaches the user in `reply`.
    """
    if not isinstance(arguments, str):
        return ["bukan JSON valid"]
    try:
        args: Any = json.loads(arguments)
    except json.JSONDecodeError as exc:
        return [f"bukan JSON valid ({exc})"]
    if not isinstance(args, dict):
        return ["harus berupa JSON object"]

    errors: list[str] = []

    for name in REQUIRED_FIELDS:
        value = args.get(name)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{name} kosong atau tidak diisi")

    for name in sorted(set(args) - set(REQUIRED_FIELDS) - set(OPTIONAL_FIELDS)):
        errors.append(f"{name} bukan argumen create_alokasi")

    # Optional fields: if sent at all, they must carry real content.
    for name in OPTIONAL_FIELDS:
        if name in args:
            value = args[name]
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{name} kosong atau tidak diisi")

    tanggal = args.get("tanggal")
    if isinstance(tanggal, str) and tanggal.strip() and not _is_real_date(tanggal):
        errors.append(
            f"tanggal harus tanggal kalender valid YYYY-MM-DD, dapat {tanggal!r}"
        )

    for name in ("jam_mulai", "jam_selesai"):
        value = args.get(name)
        if isinstance(value, str) and value.strip() and not _is_valid_time(value):
            errors.append(
                f"{name} harus HH:MM 24 jam (jam 00-23, menit 00-59), dapat {value!r}"
            )

    # Only compare order when both times are well-formed, to avoid a crash.
    if (
        isinstance(args.get("jam_mulai"), str)
        and isinstance(args.get("jam_selesai"), str)
        and _is_valid_time(args["jam_mulai"])
        and _is_valid_time(args["jam_selesai"])
        and _minutes(args["jam_selesai"]) <= _minutes(args["jam_mulai"])
    ):
        errors.append(
            f"jam_selesai harus setelah jam_mulai, dapat "
            f"{args['jam_mulai']} - {args['jam_selesai']}"
        )

    return errors
