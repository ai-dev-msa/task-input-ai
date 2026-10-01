from datetime import datetime, timezone
from types import SimpleNamespace

from alokasi_agent import run
from alokasi_agent.schema import CREATE_ALOKASI_TOOL
from alokasi_agent.llm import to_openai_tools

EXAMPLE_MESSAGE = (
    "Isikan alokasi untuk Imam Ihsani tanggal 29 September 2026 dengan pekerjaan "
    "Development Modul PPN dari jam 09 pagi sampai 12 siang, nama proyeknya OPRS Divisi WIN 2026"
)
SAMPLE_ARGUMENTS = (
    '{"nama_karyawan":"Imam Ihsani","nama_proyek":"OPRS Divisi WIN 2026",'
    '"tanggal":"2026-09-29","jenis_pekerjaan":"Development Modul PPN",'
    '"jam_mulai":"09:00","jam_selesai":"12:00"}'
)
PINNED_NOW = datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc)
EMPLOYEES = ["Imam Ihsani", "Budi Santoso"]
PROJECTS = ["OPRS Divisi WIN 2026"]
USER = "Andi Wijaya"


class StubClient:
    def __init__(self, replies):
        self._replies = list(replies)
        self.calls: list[dict] = []

    def complete(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        return SimpleNamespace(
            choices=[SimpleNamespace(message=self._replies.pop(0))]
        )


def tool_reply(arguments=SAMPLE_ARGUMENTS, content=None):
    call = SimpleNamespace(function=SimpleNamespace(name="create_alokasi", arguments=arguments))
    return SimpleNamespace(content=content, tool_calls=[call])


def text_reply(content):
    return SimpleNamespace(content=content, tool_calls=None)


def call_run(client, raw_message=EXAMPLE_MESSAGE, **kwargs):
    kwargs.setdefault("user_name", USER)
    kwargs.setdefault("employees", EMPLOYEES)
    kwargs.setdefault("projects", PROJECTS)
    kwargs.setdefault("now", PINNED_NOW)
    kwargs.setdefault("client", client)
    return run(raw_message, **kwargs)


def test_tool_call_builds_envelope():
    env, history = call_run(StubClient([tool_reply()]), user_id="U-01")
    assert env.success is True
    assert env.type == "function_call"
    assert env.function_name == "create_alokasi"
    assert env.arguments == SAMPLE_ARGUMENTS
    assert env.raw_message == EXAMPLE_MESSAGE
    assert env.user_id == "U-01"
    assert env.reply is None
    assert [turn["role"] for turn in history] == ["user", "assistant"]
    assert history[0]["content"] == EXAMPLE_MESSAGE


def test_text_reply_builds_envelope():
    env, history = call_run(StubClient([text_reply("Untuk proyek apa alokasi ini?")]))
    assert env.success is True
    assert env.type == "text"
    assert env.function_name == ""
    assert env.arguments == ""
    assert env.reply == "Untuk proyek apa alokasi ini?"
    assert env.raw_message == EXAMPLE_MESSAGE
    assert [turn["role"] for turn in history] == ["user", "assistant"]


def test_history_threading_across_confirmation():
    stub1 = StubClient([text_reply("... Benar?")])
    _, history1 = call_run(stub1)
    assert len(stub1.calls[0]["messages"]) == 2

    stub2 = StubClient([tool_reply()])
    _, history2 = call_run(stub2, raw_message="ya", history=history1)

    sent = stub2.calls[0]["messages"]
    assert [turn["role"] for turn in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == EXAMPLE_MESSAGE
    assert sent[2]["content"] == "... Benar?"
    assert sent[3]["content"] == "ya"
    assert [turn["role"] for turn in history1] == ["user", "assistant"]
    assert [turn["role"] for turn in history2] == ["user", "assistant", "user", "assistant"]
    assert history2[0]["content"] == EXAMPLE_MESSAGE
    assert history2[3]["content"] == ""


def test_tool_call_reply_carries_model_content():
    env, _ = call_run(StubClient([tool_reply(content="Berikut ringkasannya.")]))
    assert env.type == "function_call"
    assert env.reply == "Berikut ringkasannya."


def test_first_tool_call_wins():
    first = SimpleNamespace(
        function=SimpleNamespace(name="create_alokasi", arguments=SAMPLE_ARGUMENTS)
    )
    second = SimpleNamespace(function=SimpleNamespace(name="other", arguments="{}"))
    reply = SimpleNamespace(content=None, tool_calls=[first, second])
    env, _ = call_run(StubClient([reply]))
    assert env.function_name == "create_alokasi"
    assert env.arguments == SAMPLE_ARGUMENTS


def test_text_reply_with_none_content_normalizes_history():
    env, history = call_run(StubClient([text_reply(None)]))
    assert env.reply is None
    assert history[1] == {"role": "assistant", "content": ""}


def test_system_prompt_carries_injected_context():
    stub = StubClient([text_reply("ok")])
    call_run(stub)
    system = stub.calls[0]["messages"][0]
    assert system["role"] == "system"
    assert "Rabu, 30 September 2026, 14:05 WIB" in system["content"]
    assert f"Logged-in user: {USER}" in system["content"]
    assert "Valid employees: Imam Ihsani, Budi Santoso" in system["content"]


def test_tools_attached_match_contract():
    stub = StubClient([text_reply("ok")])
    call_run(stub)
    assert stub.calls[0]["tools"] == to_openai_tools(CREATE_ALOKASI_TOOL)


def test_history_defaults_are_independent():
    stub = StubClient([text_reply("a"), text_reply("b")])
    _, hist1 = call_run(stub)
    _, hist2 = call_run(stub, raw_message="second")
    assert len(hist1) == 2
    assert len(hist2) == 2
    assert hist1 is not hist2
