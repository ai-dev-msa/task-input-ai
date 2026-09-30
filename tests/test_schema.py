import json

import pytest
from pydantic import ValidationError

from alokasi_agent.schema import CreateAlokasiArgs

SAMPLE_ARGS = {
    "nama_karyawan": "Imam Ihsani",
    "nama_proyek": "OPRS Divisi WIN 2026",
    "tanggal": "2026-09-29",
    "jenis_pekerjaan": "Development Modul PPN",
    "jam_mulai": "09:00",
    "jam_selesai": "12:00",
}


def test_sample_arguments_validate_and_round_trip():
    args = CreateAlokasiArgs.model_validate(SAMPLE_ARGS)
    assert args.model_dump() == SAMPLE_ARGS
    assert CreateAlokasiArgs.model_validate_json(args.model_dump_json()) == args


def test_all_six_fields_are_required():
    schema = CreateAlokasiArgs.model_json_schema()
    assert set(schema["required"]) == set(SAMPLE_ARGS)
    assert len(schema["required"]) == 6


@pytest.mark.parametrize(
    "field,value",
    [
        ("tanggal", "29-09-2026"),
        ("tanggal", "2026/09/29"),
        ("tanggal", "2026-9-29"),
        ("jam_mulai", "9:00"),
        ("jam_selesai", "12.00"),
    ],
)
def test_malformed_date_or_time_is_rejected(field, value):
    with pytest.raises(ValidationError):
        CreateAlokasiArgs.model_validate({**SAMPLE_ARGS, field: value})


def test_missing_field_is_rejected():
    incomplete = {k: v for k, v in SAMPLE_ARGS.items() if k != "jam_selesai"}
    with pytest.raises(ValidationError):
        CreateAlokasiArgs.model_validate(incomplete)


def test_unknown_argument_is_rejected():
    with pytest.raises(ValidationError):
        CreateAlokasiArgs.model_validate({**SAMPLE_ARGS, "kode_proyek": "x"})


from pathlib import Path

from alokasi_agent.schema import CREATE_ALOKASI_TOOL

GOLDEN_PATH = Path(__file__).parent / "golden" / "create_alokasi_input_schema.json"


def test_tool_has_provider_neutral_shape():
    assert set(CREATE_ALOKASI_TOOL) == {"name", "description", "input_schema"}
    assert CREATE_ALOKASI_TOOL["name"] == "create_alokasi"
    assert CREATE_ALOKASI_TOOL["description"]


def test_input_schema_declares_formats():
    props = CREATE_ALOKASI_TOOL["input_schema"]["properties"]
    assert props["tanggal"]["pattern"] == "^\\d{4}-\\d{2}-\\d{2}$"
    assert props["jam_mulai"]["pattern"] == "^\\d{2}:\\d{2}$"
    assert props["jam_selesai"]["pattern"] == "^\\d{2}:\\d{2}$"


def test_input_schema_matches_golden_snapshot():
    actual = json.dumps(CREATE_ALOKASI_TOOL["input_schema"], indent=2, sort_keys=True) + "\n"
    expected = GOLDEN_PATH.read_text(encoding="utf-8")
    assert actual == expected, (
        "Tool input_schema changed. If intentional, regenerate the golden file:\n"
        "  .venv\\Scripts\\python.exe scripts\\update_golden.py"
    )


from alokasi_agent.schema import HasilCI3, ResponseEnvelope

SAMPLE_ENVELOPE = {
    "arguments": '{"nama_karyawan":"Imam Ihsani","nama_proyek":"OPRS Divisi WIN 2026",'
    '"tanggal":"2026-09-29","jenis_pekerjaan":"Development Modul PPN",'
    '"jam_mulai":"09:00","jam_selesai":"12:00"}',
    "function_name": "create_alokasi",
    "hasil_ci3": {
        "data": {
            "Cabang": "WIN - Pusat",
            "Jenis Alokasi": "Manpower",
            "Jenis Pekerjaan": "Development Modul PPN",
            "Jenis Proyek": "OPRS",
            "Kode Proyek": "26.01.000.00.0102.0002",
            "Nama Alokasi": "Imam Ihsani",
            "Nama Proyek": "OPRS Divisi WIN 2026",
            "RecID": 10089283,
            "Tanggal": "2026-09-29",
            "bagian": "System",
            "jam_mulai": "09:00",
            "jam_selesai": "12:00",
            "keterangan": None,
            "ketercapaian": None,
            "kode_karyawan": "WIN.01.2023.18",
            "persentase_hasil": None,
            "tanggal_input": "2026-09-29 16:37:41",
        },
        "database": "TESTING - 192.168.1.94",
        "message": "Alokasi berhasil dibuat",
        "success": True,
        "type": "created",
    },
    "raw_message": "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan "
    "pekerjaan Development Modul PPN dari jam 09 pagi sampai 12 siang, "
    "nama proyeknya OPRS Divisi WIN 2026",
    "success": True,
    "type": "function_call",
    "user_id": None,
}


def test_envelope_parses_full_sample():
    envelope = ResponseEnvelope.model_validate(SAMPLE_ENVELOPE)
    assert envelope.success is True
    assert envelope.type == "function_call"
    assert envelope.function_name == "create_alokasi"
    assert json.loads(envelope.arguments) == SAMPLE_ARGS
    assert envelope.raw_message.startswith("Isikan alokasi")
    assert envelope.user_id is None


def test_hasil_ci3_parses_sample_data():
    envelope = ResponseEnvelope.model_validate(SAMPLE_ENVELOPE)
    hasil = envelope.hasil_ci3
    assert hasil is not None
    assert hasil.success is True
    assert hasil.type == "created"
    assert hasil.database == "TESTING - 192.168.1.94"
    assert hasil.data["kode_karyawan"] == "WIN.01.2023.18"
    assert hasil.data["RecID"] == 10089283


def test_hasil_ci3_tolerates_unknown_fields():
    hasil = HasilCI3.model_validate(
        {"success": True, "type": "created", "message": "ok", "database": "TESTING", "field_baru": 1}
    )
    assert hasil.model_extra["field_baru"] == 1


def test_envelope_tolerates_unknown_fields():
    envelope = ResponseEnvelope.model_validate({**SAMPLE_ENVELOPE, "request_id": "abc-123"})
    assert envelope.model_extra["request_id"] == "abc-123"


def test_envelope_without_hasil_ci3_defaults_to_none():
    envelope = ResponseEnvelope.model_validate(
        {
            "success": False,
            "type": "error",
            "function_name": "create_alokasi",
            "arguments": "{}",
            "raw_message": "pesan",
        }
    )
    assert envelope.hasil_ci3 is None
    assert envelope.user_id is None
