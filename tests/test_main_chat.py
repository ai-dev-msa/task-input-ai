"""The /chat write path: one POST per row, and history survives ERP errors."""
import json
import sys
import types

import pytest
import requests
from flask import Blueprint

# main.py imports server-only blueprints from /var/www/html/...; give them
# stubs so `import main` works on a dev machine.
if "modules.proyek" not in sys.modules:
    _modules_pkg = types.ModuleType("modules")
    _proyek_mod = types.ModuleType("modules.proyek")
    _proyek_mod.proyek_bp = Blueprint("proyek", __name__)
    _proyek_mod.controller = types.SimpleNamespace()
    _karyawan_mod = types.ModuleType("modules.karyawan")
    _karyawan_mod.karyawan_bp = Blueprint("karyawan", __name__)
    _routes_mod = types.ModuleType("modules.karyawan.routes")
    _routes_mod.controller = types.SimpleNamespace()
    _karyawan_mod.routes = _routes_mod
    sys.modules.update({
        "modules": _modules_pkg,
        "modules.proyek": _proyek_mod,
        "modules.karyawan": _karyawan_mod,
        "modules.karyawan.routes": _routes_mod,
    })

import main  # noqa: E402

ROW1 = {"nama_karyawan": "Imam Ihsani", "nama_proyek": "OPRS Divisi WIN 2026"}
ROW2 = {"nama_karyawan": "Budi Santoso", "nama_proyek": "OPRS Divisi WIN 2026"}
TWO_ROW_ARGUMENTS = json.dumps([ROW1, ROW2])
# .text is required: main.py prints the raw response body per row.
OK_RESPONSE = types.SimpleNamespace(
    status_code=200, text="ok", json=lambda: {"success": True}
)


def envelope_with(arguments, history=None):
    """A run() stub whose envelope carries `arguments` and `history`."""
    def fake_run(*args, **kwargs):
        envelope = {
            "success": True,
            "type": "function_call",
            "function_name": "create_alokasi",
            "arguments": arguments,
            "reply": None,
            "history": history or [],
        }
        return envelope, envelope["history"]
    return fake_run


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "get_projects", lambda: [])
    monkeypatch.setattr(main, "get_employees", lambda: [])
    monkeypatch.setattr(main, "get_erp_token", lambda: "token-test")
    monkeypatch.setattr(
        main.requests, "get",
        lambda *args, **kwargs: types.SimpleNamespace(status_code=200, text="ok"),
    )
    main.app.config["TESTING"] = True
    with main.app.test_client() as test_client:
        yield test_client


def test_second_row_failure_still_reports_first_row(client, monkeypatch):
    monkeypatch.setattr(main, "run", envelope_with(TWO_ROW_ARGUMENTS))
    replies = [OK_RESPONSE, requests.exceptions.ConnectionError("erp down")]

    def fake_post(*args, **kwargs):
        item = replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(main.requests, "post", fake_post)
    data = client.post("/chat", json={"message": "ya"}).get_json()
    assert data["success"] is True
    assert data["type"] == "function_call"
    assert len(data["hasil_ci3"]) == 2
    assert data["hasil_ci3"][0] == {"success": True}
    assert data["hasil_ci3"][1]["success"] is False
    assert "Baris 2" in data["hasil_ci3"][1]["message"]


def test_single_row_keeps_object_hasil_ci3(client, monkeypatch):
    monkeypatch.setattr(main, "run", envelope_with(json.dumps(ROW1)))
    monkeypatch.setattr(main.requests, "post", lambda *a, **k: OK_RESPONSE)
    data = client.post("/chat", json={"message": "ya"}).get_json()
    assert data["type"] == "function_call"
    assert isinstance(data["hasil_ci3"], dict)
    assert data["hasil_ci3"]["success"] is True


def test_erp_error_returns_the_updated_history(client, monkeypatch):
    history = [
        {"role": "user", "content": "ya"},
        {"role": "assistant", "content": ""},
    ]
    monkeypatch.setattr(main, "run", envelope_with(TWO_ROW_ARGUMENTS, history=history))

    def raise_get(*args, **kwargs):
        raise RuntimeError("validate down")

    monkeypatch.setattr(main.requests, "get", raise_get)
    sent = [{"role": "user", "content": "old history"}]
    data = client.post("/chat", json={"message": "ya", "history": sent}).get_json()
    assert data["type"] == "error"
    assert data["history"] == history
