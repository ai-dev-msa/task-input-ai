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
)

# Optional fields the model may add; absent means "user did not provide".
OPTIONAL_FIELDS = (
    "jam_selesai",
    "keterangan",
    "jobdesc",
    "planning",
    "kategori_pekerjaan",
)

CREATE_ALOKASI_DESCRIPTION = (
    "Buat satu baris alokasi kerja karyawan untuk satu tanggal. "
    "Wajib: nama_karyawan, nama_proyek, tanggal, jenis_pekerjaan, jam_mulai. "
    "Opsional: jam_selesai dan keterangan. Jika user tidak menulisnya, "
    "isi null dan lanjutkan; jangan ditanyakan. "
    "Jika ada beberapa baris, panggil fungsi ini sekali per baris, "
    "semuanya dalam satu balasan."
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
                "description": (
                    "Jam selesai HH:MM, contoh: 12:00. Opsional: "
                    "null jika user tidak menyebutnya"
                ),
                "pattern": "^\\d{2}:\\d{2}$",
                "title": "Jam Selesai",
                "type": ["string", "null"],
            },
            "jenis_pekerjaan": {
                "description": "Uraian pekerjaan, contoh: Development Modul PPN",
                "minLength": 1,
                "title": "Jenis Pekerjaan",
                "type": "string",
            },
            "keterangan": {
                "description": (
                    "Keterangan hasil atau detail pekerjaan. "
                    "Wajib diisi jika jam_selesai diisi. "
                    "Status/hasil pekerjaan, tanpa kata label (review/hasil/keterangan). "
                    "Boleh bracket [a/b/c/d] (contoh: [2/1/1/0]) atau teks biasa "
                    "(contoh: sudah selesai)"
                ),
                "minLength": 1,
                "title": "Keterangan",
                "type": ["string", "null"],
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
            "tanggal": {
                "description": "Tanggal pekerjaan dalam format YYYY-MM-DD, contoh: 2026-09-29",
                "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                "title": "Tanggal",
                "type": "string",
            },
            "jobdesc": { #tambahan dari ihsan 2 11 2026
                "description": (
                    "Nama jobdesc sesuai pilihan pengguna. "
                    "Kirim sebagai teks, bukan ID. Jangan mengarang nama."
                ),
                "title": "Jobdesc",
                "type": "string",
                "minLength": 1,
            },
            "planning": { #tambahan dari ihsan 2 11 2026
                "description": (
                    "Nama aktivitas planning sesuai pilihan pengguna. "
                    "Kirim sebagai teks, bukan ID. Jangan mengarang nama."
                ),
                "title": "Planning",
                "type": "string",
                "minLength": 1,
            },
            "kategori_pekerjaan": {
                "title": "Kategori",
                "type": "string",
                "minLength": 1,
                "description": (
                    "Nama kategori pekerjaan sesuai BoQ proyek. "
                    "Wajib untuk karyawan MSA divisi 1. "
                    "Untuk pekerjaan Standby, isi dengan Standby."
                ),
            },
            "plan_qty": {
                "title": "Qty Plan",
                "type": "integer",
                "minimum": 1,
                "description": (
                    "Jumlah rencana pekerjaan dalam angka. "
                    "Wajib untuk karyawan MSA divisi 1, kecuali Standby "
                    "yang otomatis menggunakan nilai 1."
                ),
            },
            # "boq_id": {
            #     "type": ["integer", "null"],
            #     "description": "ID BOQ. Tidak wajib untuk kategori Standby."
            # },
            # "tim_pekerjaan": {
            #     "description": "Nama anggota tim, dipisah koma, contoh: Bimo Aditya Pangestu, Janie Natalie",
            #     "minLength": 1,
            #     "title": "Tim Pekerjaan",
            #     "type": "string",
            # },
        },
        "required": list(REQUIRED_FIELDS),
        "title": "CreateAlokasiArgs",
        "type": "object",
    },
}

CHECK_PROJECT_TOOL = { #dari ihsan
    "name": "check_project",
    "description": (
        "Memeriksa apakah suatu proyek terdaftar di MSA. "
        "Gunakan untuk pertanyaan tentang keberadaan, ketersediaan, "
        "atau status terdaftarnya proyek. Tidak membuat alokasi."
    ),
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "nama_proyek": {
                "type": "string",
                "description": (
                    "Nama proyek yang ingin diperiksa berdasarkan "
                    "permintaan pengguna."
                ),
                "minLength": 1,
            }
        },
        "required": ["nama_proyek"],
    },
}

FIND_EMPLOYEE_DESCRIPTION = (
    "Cocokkan nama dengan daftar karyawan. Panggil untuk setiap nama_karyawan "
    "sebelum create_alokasi atau find_alokasi; gunakan ejaan yang dikembalikan alat ini."
)

FIND_EMPLOYEE_TOOL = {
    "name": "find_employee",
    "description": FIND_EMPLOYEE_DESCRIPTION,
    "input_schema": {
        "additionalProperties": False,
        "properties": {
            "name": {
                "description": "Nama karyawan sesuai tulisan user, contoh: Imam Ihsani",
                "minLength": 1,
                "title": "Name",
                "type": "string",
            },
        },
        "required": ["name"],
        "title": "FindEmployeeArgs",
        "type": "object",
    },
}

FIND_PROJECT_TOOL = {
    "name": "find_project",
    "description": (
        "Cocokkan nama proyek dengan daftar proyek. Panggil untuk setiap nama_proyek "
        "sebelum create_alokasi atau find_alokasi. Kirim nama proyek selengkap yang ditulis user, "
        "jangan dipotong atau disingkat. Gunakan ejaan yang dikembalikan alat ini. "
        "Jika hasilnya berisi beberapa kandidat, tanyakan ke user yang mana."
    ),
    "input_schema": {
        "additionalProperties": False,
        "properties": {
            "name": {
                "description": (
                    "Nama proyek lengkap persis seperti tulisan user, "
                    "contoh: OPRS Divisi WIN 2026. Jangan hanya awalannya (misal 'OPRS')."
                ),
                "minLength": 1,
                "title": "Name",
                "type": "string",
            },
        },
        "required": ["name"],
        "title": "FindProjectArgs",
        "type": "object",
    },
}

FIND_ALOKASI_TOOL = {
    "name": "find_alokasi",
    "description": (
        "Cari alokasi kerja yang sudah ada, untuk diubah. Wajib: nama_alokasi, "
        "tanggal, jenis_pekerjaan, dan TEPAT SATU dari nama_proyek atau "
        "kode_proyek (jangan keduanya). Panggil find_employee dan find_project "
        "lebih dulu. Hasilnya berisi id_edit untuk update_alokasi."
    ),
    "input_schema": {
        "additionalProperties": False,
        "properties": {
            "nama_alokasi": {
                "description": (
                    "Nama karyawan pemilik alokasi, sesuai hasil find_employee"
                ),
                "minLength": 1,
                "title": "Nama Alokasi",
                "type": "string",
            },
            "tanggal": {
                "description": "Tanggal alokasi YYYY-MM-DD, contoh: 2026-11-10",
                "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                "title": "Tanggal",
                "type": "string",
            },
            "jenis_pekerjaan": {
                "description": (
                    "Uraian pekerjaan alokasi yang dicari, boleh sebagian "
                    "kata, contoh: development endpoint"
                ),
                "minLength": 1,
                "title": "Jenis Pekerjaan",
                "type": "string",
            },
            "nama_proyek": {
                "description": (
                    "Nama proyek lengkap sesuai hasil find_project. "
                    "Isi ini ATAU kode_proyek, jangan keduanya."
                ),
                "minLength": 1,
                "title": "Nama Proyek",
                "type": "string",
            },
            "kode_proyek": {
                "description": (
                    "Kode proyek, hanya jika user menulis kodenya. "
                    "Isi ini ATAU nama_proyek, jangan keduanya."
                ),
                "minLength": 1,
                "title": "Kode Proyek",
                "type": "string",
            },
        },
        "required": ["nama_alokasi", "tanggal", "jenis_pekerjaan"],
        "title": "FindAlokasiArgs",
        "type": "object",
    },
}

UPDATE_FIELDS = ("jam_mulai", "jam_selesai", "jenis_pekerjaan", "keterangan")

UPDATE_ALOKASI_TOOL = {
    "name": "update_alokasi",
    "description": (
        "Ubah satu alokasi kerja yang sudah ada. Panggil hanya setelah user "
        "mengonfirmasi baris ubahan. Wajib: id_edit dari hasil find_alokasi. "
        "Kirim HANYA field yang diubah; field yang tidak dikirim tidak berubah. "
        "Satu panggilan per alokasi."
    ),
    "input_schema": {
        "additionalProperties": False,
        "properties": {
            "id_edit": {
                "description": "ID alokasi dari hasil find_alokasi, contoh: J98BO65CQ3",
                "minLength": 1,
                "title": "ID Edit",
                "type": "string",
            },
            "jam_mulai": {
                "description": "Jam mulai baru HH:MM, contoh: 09:00",
                "pattern": "^\\d{2}:\\d{2}$",
                "title": "Jam Mulai",
                "type": "string",
            },
            "jam_selesai": {
                "description": "Jam selesai baru HH:MM, contoh: 13:00",
                "pattern": "^\\d{2}:\\d{2}$",
                "title": "Jam Selesai",
                "type": "string",
            },
            "jenis_pekerjaan": {
                "description": "Uraian pekerjaan baru",
                "minLength": 1,
                "title": "Jenis Pekerjaan",
                "type": "string",
            },
            "keterangan": {
                "description": "Keterangan hasil baru, aturan sama seperti create_alokasi",
                "minLength": 1,
                "title": "Keterangan",
                "type": "string",
            },
        },
        "required": ["id_edit"],
        "title": "UpdateAlokasiArgs",
        "type": "object",
    },
}

CHECK_PROJECT_TOOL = { #dari ihsan
    "name": "check_project",
    "description": (
        "Memeriksa apakah suatu proyek terdaftar di MSA. "
        "Gunakan untuk pertanyaan tentang keberadaan, ketersediaan, "
        "atau status terdaftarnya proyek. Tidak membuat alokasi."
    ),
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "nama_proyek": {
                "type": "string",
                "description": (
                    "Nama proyek yang ingin diperiksa berdasarkan "
                    "permintaan pengguna."
                ),
                "minLength": 1,
            }
        },
        "required": ["nama_proyek"],
    },
}

CHECK_EMPLOYEE_TOOL = { #dari ihsan
    "name": "check_employee",
    "description": (
        "Memeriksa apakah karyawan terdaftar sebagai karyawan aktif di MSA. "
        "Gunakan hanya ketika pengguna bertanya tentang keberadaan karyawan. "
        "Jangan gunakan check_project untuk pertanyaan karyawan. "
        "Tidak membuat alokasi."
    ),
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "nama_karyawan": {
                "type": "string",
                "description": (
                    "Nama atau kata kunci nama karyawan yang ingin dicari."
                ),
                "minLength": 1,
            }
        },
        "required": ["nama_karyawan"],
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

    # Optional fields: if sent with a value, it must carry real content.
    # Explicit null means the same as the key being absent, so it is accepted.
    for name in OPTIONAL_FIELDS:
        value = args.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            continue  # None or blank means "not provided"
        if not isinstance(value, str):
            errors.append(f"{name} harus berupa teks")

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

def validate_update_arguments(arguments: str) -> list[str]:
    """Return every problem with update_alokasi arguments. [] means safe.

    Order check only runs when both times are sent; when just one is sent,
    the agent compares it with the row's current value (a later step).
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

    id_edit = args.get("id_edit")
    if not isinstance(id_edit, str) or not id_edit.strip():
        errors.append("id_edit kosong atau tidak diisi")

    for name in sorted(set(args) - {"id_edit"} - set(UPDATE_FIELDS)):
        errors.append(f"{name} bukan argumen update_alokasi")

    sent = [name for name in UPDATE_FIELDS if name in args]
    if not sent:
        errors.append("tidak ada field yang diubah")

    for name in sent:
        value = args[name]
        if not isinstance(value, str) or not value.strip():
            errors.append(
                f"{name} harus teks tidak kosong; kirim hanya field yang diubah"
            )

    for name in ("jam_mulai", "jam_selesai"):
        value = args.get(name)
        if isinstance(value, str) and value.strip() and not _is_valid_time(value):
            errors.append(
                f"{name} harus HH:MM 24 jam (jam 00-23, menit 00-59), dapat {value!r}"
            )

    mulai, selesai = args.get("jam_mulai"), args.get("jam_selesai")
    if (
        isinstance(mulai, str)
        and isinstance(selesai, str)
        and _is_valid_time(mulai)
        and _is_valid_time(selesai)
        and _minutes(selesai) <= _minutes(mulai)
    ):
        errors.append(
            f"jam_selesai harus setelah jam_mulai, dapat {mulai} - {selesai}"
        )

    return errors

def times_in_order(mulai: str, selesai: str) -> bool:
    """True when selesai is later than mulai; malformed times are not judged here."""
    if not (_is_valid_time(mulai) and _is_valid_time(selesai)):
        return True
    return _minutes(selesai) > _minutes(mulai)
