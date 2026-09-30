# FR-01: Tool Schema and Contract (`create_alokasi`) Implementation Plan

> **Superseded (2026-09-30, boundary decision A):** Task 3's `HasilCI3` model and `ResponseEnvelope.hasil_ci3` field were removed after completion — this repo is AI-only and does not model CI3's response. The envelope is now `success`, `type`, `function_name`, `arguments`, `raw_message`, `user_id`. Everything else in this plan stands.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One shared contract module holding the `create_alokasi` tool definition and the response envelope, imported by the prompt, the validator, and the tests.

**Architecture:** Pydantic v2 models are the single source of truth. `CreateAlokasiArgs.model_json_schema()` generates the tool's `input_schema`, so the JSON the LLM sees and the JSON the validator enforces can never drift. A golden-file test freezes the emitted schema so any accidental change fails CI.

**Tech Stack:** Python 3.14 (venv via `py -3`), Pydantic v2, pytest, src layout.

## Global Constraints

- All 6 arguments are **required**: `nama_karyawan`, `nama_proyek`, `tanggal`, `jenis_pekerjaan`, `jam_mulai`, `jam_selesai`.
- `tanggal` format `YYYY-MM-DD`; `jam_mulai`/`jam_selesai` format `HH:MM` (§8.2).
- Tool shape is provider-neutral: exactly `{"name", "description", "input_schema"}`.
- Envelope `arguments` is a JSON **string**, not an object (§8.5).
- `hasil_ci3` and the envelope allow unknown extra fields; `CreateAlokasiArgs` forbids them.
- Out of scope: `jam_selesai > jam_mulai` (FR-05), envelope-building helpers (FR-04), provider tool format (FR-02).
- All commands run from the repo root `C:\Users\ACER\Documents\GitHub\task-input-ai`.
- Shell is PowerShell 5.1: never use `>` to redirect Python output to a file (it writes UTF-16); use `Path.write_text(..., encoding="utf-8")`.

---

### Task 1: Environment scaffold and `CreateAlokasiArgs`

**Files:**
- Create: `pyproject.toml`
- Create: `src/alokasi_agent/__init__.py`
- Create: `src/alokasi_agent/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `CreateAlokasiArgs(BaseModel)` with six required `str` fields; importable as `from alokasi_agent.schema import CreateAlokasiArgs`.

- [ ] **Step 1: Create the virtual environment**

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
```

Expected: pip reports a version (3.14.7 venv).

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "alokasi-agent"
version = "0.1.0"
description = "Natural-language allocation agent for create_alokasi"
requires-python = ">=3.11"
dependencies = ["pydantic>=2.7,<3"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Create the package files**

`src/alokasi_agent/__init__.py` — empty file.

`src/alokasi_agent/schema.py`:

```python
from pydantic import BaseModel, ConfigDict, Field

CREATE_ALOKASI_DESCRIPTION = (
    "Buat satu baris alokasi kerja karyawan untuk satu tanggal: "
    "nama karyawan, nama proyek, tanggal, jenis pekerjaan, dan jam mulai/selesai."
)


class CreateAlokasiArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    nama_karyawan: str = Field(
        description="Nama lengkap karyawan, contoh: Imam Ihsani"
    )
    nama_proyek: str = Field(
        description="Nama proyek, contoh: OPRS Divisi WIN 2026"
    )
    tanggal: str = Field(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Tanggal pekerjaan dalam format YYYY-MM-DD, contoh: 2026-09-29",
    )
    jenis_pekerjaan: str = Field(
        description="Uraian pekerjaan, contoh: Development Modul PPN"
    )
    jam_mulai: str = Field(
        pattern=r"^\d{2}:\d{2}$",
        description="Jam mulai dalam format HH:MM, contoh: 09:00",
    )
    jam_selesai: str = Field(
        pattern=r"^\d{2}:\d{2}$",
        description="Jam selesai dalam format HH:MM, contoh: 12:00",
    )
```

- [ ] **Step 4: Install the package in editable mode**

```powershell
.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Expected: `Successfully installed alokasi-agent ...` with pydantic v2 and pytest pulled in. This is what makes `from alokasi_agent.schema import ...` resolve (src layout is not on `sys.path` otherwise).

- [ ] **Step 5: Write the failing tests** — create `tests/test_schema.py`:

```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_schema.py -v
```

Expected: 9 passed (1 + 1 + 5 parametrized + 1 + 1).

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml src tests
git commit -m "feat(fr-01): add create_alokasi argument schema"
```

*(Ask the user for go-ahead before committing.)*

---

### Task 2: `CREATE_ALOKASI_TOOL` and the golden schema snapshot

**Files:**
- Modify: `src/alokasi_agent/schema.py`
- Create: `tests/golden/create_alokasi_input_schema.json`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: `CreateAlokasiArgs` and `CREATE_ALOKASI_DESCRIPTION` from Task 1.
- Produces: `CREATE_ALOKASI_TOOL: dict` with keys `name`, `description`, `input_schema`. Later tasks (FR-02 prompt, FR-04 call) import this exact name.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_schema.py`:

```python
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
```

Add `import json` to the existing import block at the top of the file.

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_schema.py -v
```

Expected: `ImportError: cannot import name 'CREATE_ALOKASI_TOOL'`.

- [ ] **Step 3: Implement the tool definition** — append to `src/alokasi_agent/schema.py`:

```python
from typing import Any

CREATE_ALOKASI_TOOL: dict[str, Any] = {
    "name": "create_alokasi",
    "description": CREATE_ALOKASI_DESCRIPTION,
    "input_schema": CreateAlokasiArgs.model_json_schema(),
}
```

(Keep `from pydantic import ...` as the import; add `from typing import Any` alongside it.)

- [ ] **Step 4: Create `scripts/update_golden.py`**

```python
import json
from pathlib import Path

from alokasi_agent.schema import CREATE_ALOKASI_TOOL

TARGET = (
    Path(__file__).resolve().parent.parent
    / "tests"
    / "golden"
    / "create_alokasi_input_schema.json"
)
TARGET.parent.mkdir(parents=True, exist_ok=True)
TARGET.write_text(
    json.dumps(CREATE_ALOKASI_TOOL["input_schema"], indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
print(f"wrote {TARGET}")
```

- [ ] **Step 5: Generate the golden file**

```powershell
.venv\Scripts\python.exe scripts\update_golden.py
```

Expected: `wrote ...tests\golden\create_alokasi_input_schema.json`.

- [ ] **Step 6: Run the tests to verify they pass**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_schema.py -v
```

Expected: all tests pass, including `test_input_schema_matches_golden_snapshot`.

- [ ] **Step 7: Commit**

```powershell
git add src tests scripts
git commit -m "feat(fr-01): add create_alokasi tool definition with golden schema"
```

*(Ask the user for go-ahead before committing.)*

---

### Task 3: Response envelope (`HasilCI3`, `ResponseEnvelope`)

**Files:**
- Modify: `src/alokasi_agent/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `HasilCI3(BaseModel)` and `ResponseEnvelope(BaseModel)` (fields exactly as in the spec §8.4/§8.5). FR-03/FR-04 build these; FR-11 reads `hasil_ci3.success`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_schema.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
.venv\Scripts\python.exe -m pytest tests/test_schema.py -v
```

Expected: `ImportError: cannot import name 'HasilCI3'`.

- [ ] **Step 3: Implement the envelope models** — append to `src/alokasi_agent/schema.py`:

```python
class HasilCI3(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool
    type: str
    message: str
    database: str
    data: dict[str, Any] = Field(default_factory=dict)


class ResponseEnvelope(BaseModel):
    model_config = ConfigDict(extra="allow")

    success: bool
    type: str
    function_name: str
    arguments: str
    hasil_ci3: HasilCI3 | None = None
    raw_message: str
    user_id: str | None = None
```

- [ ] **Step 4: Run the full suite**

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

Expected: all tests pass (Task 1 + Task 2 + Task 3).

- [ ] **Step 5: Commit**

```powershell
git add src tests
git commit -m "feat(fr-01): add response envelope models"
```

*(Ask the user for go-ahead before committing.)*

---

## Done criteria (FR-01)

The schema lives in `src/alokasi_agent/schema.py` and is imported by the tool definition, the tests — and from FR-02 onward, the prompt builder and the validator. Nothing else defines the contract.
