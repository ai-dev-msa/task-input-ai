from types import SimpleNamespace

import pytest

from alokasi_agent.llm import complete, load_config, to_openai_tools
from alokasi_agent.schema import CREATE_ALOKASI_TOOL

OVERRIDE_VARS = (
    "ALOKASI_MODEL",
    "ALOKASI_TEMPERATURE",
    "ALOKASI_TIMEOUT",
    "ALOKASI_REASONING_EFFORT",
    "OPENAI_BASE_URL",
)


def _clear_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    for var in OVERRIDE_VARS:
        monkeypatch.delenv(var, raising=False)


def _stub_openai(monkeypatch, captured):
    """Replace the OpenAI SDK class with a fake that records request kwargs."""

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(model_dump=lambda: {"choices": []})

    def fake_openai(**init_kwargs):
        return SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )

    monkeypatch.setattr("alokasi_agent.llm.OpenAI", fake_openai)


def test_load_config_requires_api_key(monkeypatch):
    _clear_env(monkeypatch)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        load_config()


def test_load_config_rejects_whitespace_only_api_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        load_config()


def test_load_config_defaults_when_only_key_set(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = load_config()
    assert cfg["api_key"] == "sk-test"
    assert cfg["model"] == "gpt-4o-mini"
    assert cfg["temperature"] == 0.0
    assert cfg["timeout"] == 30.0
    assert cfg["base_url"] is None


def test_load_config_applies_overrides(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_MODEL", "gpt-4o-mini-2024-07-18")
    monkeypatch.setenv("ALOKASI_TEMPERATURE", "0.2")
    monkeypatch.setenv("ALOKASI_TIMEOUT", "12.5")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example/v1")
    cfg = load_config()
    assert cfg["model"] == "gpt-4o-mini-2024-07-18"
    assert cfg["temperature"] == 0.2
    assert cfg["timeout"] == 12.5
    assert cfg["base_url"] == "https://proxy.example/v1"


def test_load_config_rejects_non_numeric_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_TIMEOUT", "cepat")
    # ValueError comes straight from float(); no custom message needed.
    with pytest.raises(ValueError):
        load_config()


def test_load_config_reads_reasoning_effort(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_REASONING_EFFORT", "none")
    cfg = load_config()
    assert cfg["reasoning_effort"] == "none"


def test_load_config_blank_reasoning_effort_is_none(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_REASONING_EFFORT", "  ")
    cfg = load_config()
    assert cfg["reasoning_effort"] is None


def test_complete_passes_reasoning_effort_when_set(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_REASONING_EFFORT", "none")
    captured: dict = {}
    _stub_openai(monkeypatch, captured)
    result = complete([{"role": "user", "content": "hi"}])
    assert result == {"choices": []}
    assert captured["reasoning_effort"] == "none"
    assert captured["model"] == "gpt-4o-mini"


def test_complete_omits_reasoning_effort_by_default(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    captured: dict = {}
    _stub_openai(monkeypatch, captured)
    complete([{"role": "user", "content": "hi"}])
    assert "reasoning_effort" not in captured


def test_complete_uses_injected_config(monkeypatch):
    _clear_env(monkeypatch)
    captured: dict = {}
    _stub_openai(monkeypatch, captured)
    config = {
        "api_key": "sk-test",
        "model": "test-model",
        "temperature": 0.7,
        "timeout": 5.0,
        "base_url": None,
        "reasoning_effort": None,
    }
    complete([{"role": "user", "content": "hi"}], config=config)
    assert captured["model"] == "test-model"
    assert captured["temperature"] == 0.7


def test_to_openai_tools_converts_provider_neutral_contract():
    tools = to_openai_tools(CREATE_ALOKASI_TOOL)
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    function = tools[0]["function"]
    assert function["name"] == "create_alokasi"
    assert function["description"] == CREATE_ALOKASI_TOOL["description"]
    assert function["parameters"] == CREATE_ALOKASI_TOOL["input_schema"]
