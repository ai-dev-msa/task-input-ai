import pytest

from alokasi_agent.llm import LLMClient, LLMConfig, to_openai_tools
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


def test_from_env_requires_api_key(monkeypatch):
    _clear_env(monkeypatch)
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        LLMConfig.from_env()


def test_from_env_rejects_whitespace_only_api_key(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "   ")
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        LLMConfig.from_env()


def test_from_env_defaults_when_only_key_set(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    cfg = LLMConfig.from_env()
    assert cfg.api_key == "sk-test"
    assert cfg.model == "gpt-4o-mini"
    assert cfg.temperature == 0.0
    assert cfg.timeout == 30.0
    assert cfg.base_url is None


def test_from_env_applies_overrides(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_MODEL", "gpt-4o-mini-2024-07-18")
    monkeypatch.setenv("ALOKASI_TEMPERATURE", "0.2")
    monkeypatch.setenv("ALOKASI_TIMEOUT", "12.5")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example/v1")
    cfg = LLMConfig.from_env()
    assert cfg.model == "gpt-4o-mini-2024-07-18"
    assert cfg.temperature == 0.2
    assert cfg.timeout == 12.5
    assert cfg.base_url == "https://proxy.example/v1"


def test_from_env_rejects_non_numeric_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_TIMEOUT", "cepat")
    with pytest.raises(ValueError, match="ALOKASI_TIMEOUT"):
        LLMConfig.from_env()


def test_from_env_reads_reasoning_effort(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_REASONING_EFFORT", "none")
    cfg = LLMConfig.from_env()
    assert cfg.reasoning_effort == "none"


def test_from_env_blank_reasoning_effort_is_none(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("ALOKASI_REASONING_EFFORT", "  ")
    cfg = LLMConfig.from_env()
    assert cfg.reasoning_effort is None


def _stub_create(monkeypatch, client):
    captured: dict = {}
    sentinel = object()

    def fake_create(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    return captured, sentinel


def test_complete_passes_reasoning_effort_when_set(monkeypatch):
    client = LLMClient(LLMConfig(api_key="sk-test", reasoning_effort="none"))
    captured, sentinel = _stub_create(monkeypatch, client)
    result = client.complete([{"role": "user", "content": "hi"}])
    assert result is sentinel
    assert captured["reasoning_effort"] == "none"
    assert captured["model"] == "gpt-4o-mini"


def test_complete_omits_reasoning_effort_by_default(monkeypatch):
    client = LLMClient(LLMConfig(api_key="sk-test"))
    captured, _ = _stub_create(monkeypatch, client)
    client.complete([{"role": "user", "content": "hi"}])
    assert "reasoning_effort" not in captured


def test_to_openai_tools_converts_provider_neutral_contract():
    tools = to_openai_tools(CREATE_ALOKASI_TOOL)
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    function = tools[0]["function"]
    assert function["name"] == "create_alokasi"
    assert function["description"] == CREATE_ALOKASI_TOOL["description"]
    assert function["parameters"] == CREATE_ALOKASI_TOOL["input_schema"]


def test_client_keeps_injected_config():
    cfg = LLMConfig(api_key="sk-test", model="test-model", temperature=0.7, timeout=5.0)
    client = LLMClient(cfg)
    assert client.config is cfg
