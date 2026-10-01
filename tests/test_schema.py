import json
from pathlib import Path

import pytest

from alokasi_agent.schema import CREATE_ALOKASI_TOOL, validate_arguments

GOLDEN_PATH = Path(__file__).parent / "golden" / "create_alokasi_input_schema.json"

SIX_FIELDS = {
    "nama_karyawan",
    "nama_proyek",
    "tanggal",
    "jenis_pekerjaan",
    "jam_mulai",
    "jam_selesai",
}


def test_tool_has_provider_neutral_shape():
    assert set(CREATE_ALOKASI_TOOL) == {"name", "description", "input_schema"}
    assert CREATE_ALOKASI_TOOL["name"] == "create_alokasi"
    assert CREATE_ALOKASI_TOOL["description"]


def test_input_schema_declares_formats():
    props = CREATE_ALOKASI_TOOL["input_schema"]["properties"]
    assert props["tanggal"]["pattern"] == "^\\d{4}-\\d{2}-\\d{2}$"
    assert props["jam_mulai"]["pattern"] == "^\\d{2}:\\d{2}$"
    assert props["jam_selesai"]["pattern"] == "^\\d{2}:\\d{2}$"


def test_all_six_fields_are_required():
    schema = CREATE_ALOKASI_TOOL["input_schema"]
    assert set(schema["required"]) == SIX_FIELDS
    assert len(schema["required"]) == 6


def test_input_schema_matches_golden_snapshot():
    actual = json.dumps(CREATE_ALOKASI_TOOL["input_schema"], indent=2, sort_keys=True) + "\n"
    expected = GOLDEN_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "Tool input_schema changed. If intentional, regenerate the golden file:\n"
        "  .venv\\Scripts\\python.exe scripts\\update_golden.py"
    )


# --- FR-05: validate_arguments ---

VALID_ARGS = {
    "nama_karyawan": "Imam Ihsani",
    "nama_proyek": "OPRS Divisi WIN 2026",
    "tanggal": "2026-09-29",
    "jenis_pekerjaan": "Development Modul PPN",
    "jam_mulai": "09:00",
    "jam_selesai": "12:00",
}


def as_json(**overrides):
    return json.dumps({**VALID_ARGS, **overrides})


def test_validate_accepts_sample():
    assert validate_arguments(as_json()) == []


def test_validate_accepts_optional_fields():
    assert (
        validate_arguments(
            as_json(review="[1/1/1/0] Done", tim_pekerjaan="Imam Ihsani, Budi Santoso")
        )
        == []
    )


@pytest.mark.parametrize("payload", [as_json(review=""), as_json(tim_pekerjaan="   ")])
def test_validate_rejects_blank_optional_field(payload):
    assert validate_arguments(payload) != []


@pytest.mark.parametrize(
    "payload",
    [
        "bukan json {",
        "[1, 2]",
        "null",
        json.dumps({k: v for k, v in VALID_ARGS.items() if k != "jam_selesai"}),
        as_json(nama_karyawan=""),
        as_json(nama_karyawan="   "),
        json.dumps({**VALID_ARGS, "jenis_pekerjaan": None}),
        as_json(tanggal="2026-13-45"),
        as_json(tanggal="2026-9-29"),
        as_json(tanggal="29-09-2026"),
        as_json(jam_mulai="99:99"),
        as_json(jam_mulai="12:60"),
        as_json(jam_mulai="9:00"),
        as_json(jam_mulai="09:00", jam_selesai="09:00"),
        as_json(jam_mulai="12:00", jam_selesai="09:00"),
        as_json(kode_proyek="x"),
    ],
)
def test_validate_rejects_malformed_output(payload):
    assert validate_arguments(payload) != []


def test_validate_reports_every_missing_field():
    errors = validate_arguments('{"tanggal":"2026-13-45"}')
    for field in ("nama_karyawan", "nama_proyek", "jenis_pekerjaan", "jam_mulai", "jam_selesai"):
        assert any(field in error for error in errors)
    assert any("tanggal" in error for error in errors)
