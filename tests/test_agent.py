import json
from datetime import datetime, timezone

from alokasi_agent import run
from alokasi_agent.llm import to_openai_tools
from alokasi_agent.schema import CREATE_ALOKASI_TOOL

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


def make_stub(replies, calls):
    """Fake llm.complete: pop replies in order and record each request."""
    queue = list(replies)

    def complete(messages, tools=None):
        calls.append({"messages": messages, "tools": tools})
        return {"choices": [{"message": queue.pop(0)}]}

    return complete


def tool_reply(arguments=SAMPLE_ARGUMENTS, content=None):
    return {
        "content": content,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "create_alokasi", "arguments": arguments},
            }
        ],
    }


def text_reply(content):
    return {"content": content, "tool_calls": None}


def call_run(complete, raw_message=EXAMPLE_MESSAGE, **kwargs):
    kwargs.setdefault("user_name", USER)
    kwargs.setdefault("employees", EMPLOYEES)
    kwargs.setdefault("projects", PROJECTS)
    kwargs.setdefault("now", PINNED_NOW)
    kwargs.setdefault("complete", complete)
    return run(raw_message, **kwargs)


def test_tool_call_builds_envelope():
    calls = []
    env, history = call_run(make_stub([tool_reply()], calls), user_id="U-01")
    assert env["success"] is True
    assert env["type"] == "function_call"
    assert env["function_name"] == "create_alokasi"
    assert env["arguments"] == SAMPLE_ARGUMENTS
    assert env["raw_message"] == EXAMPLE_MESSAGE
    assert env["user_id"] == "U-01"
    assert env["reply"] is None
    assert [turn["role"] for turn in history] == ["user", "assistant"]
    assert history[0]["content"] == EXAMPLE_MESSAGE


def test_text_reply_builds_envelope():
    calls = []
    env, history = call_run(make_stub([text_reply("Untuk proyek apa alokasi ini?")], calls))
    assert env["success"] is True
    assert env["type"] == "text"
    assert env["function_name"] == ""
    assert env["arguments"] == ""
    assert env["reply"] == "Untuk proyek apa alokasi ini?"
    assert env["raw_message"] == EXAMPLE_MESSAGE
    assert [turn["role"] for turn in history] == ["user", "assistant"]


def test_history_threading_across_confirmation():
    calls1 = []
    _, history1 = call_run(make_stub([text_reply("... Benar?")], calls1))
    assert len(calls1[0]["messages"]) == 2

    calls2 = []
    _, history2 = call_run(
        make_stub([tool_reply()], calls2), raw_message="ya", history=history1
    )

    sent = calls2[0]["messages"]
    assert [turn["role"] for turn in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == EXAMPLE_MESSAGE
    assert sent[2]["content"] == "... Benar?"
    assert sent[3]["content"] == "ya"
    assert [turn["role"] for turn in history1] == ["user", "assistant"]
    assert [turn["role"] for turn in history2] == ["user", "assistant", "user", "assistant"]
    assert history2[0]["content"] == EXAMPLE_MESSAGE
    assert history2[3]["content"] == ""


def test_envelope_history_confirms_second_turn():
    # FR-16 done-condition: turn 2 reuses turn 1's envelope history, not the tuple.
    calls1 = []
    env1, _ = call_run(make_stub([text_reply("... Benar?")], calls1))

    calls2 = []
    env2, _ = call_run(
        make_stub([tool_reply()], calls2), raw_message="ya", history=env1["history"]
    )

    sent = calls2[0]["messages"]
    assert [turn["role"] for turn in sent] == ["system", "user", "assistant", "user"]
    assert env2["type"] == "function_call"


def test_envelope_carries_full_text_history():
    calls = []
    env, history = call_run(make_stub([tool_reply()], calls))
    assert env["history"] == history
    assert [turn["role"] for turn in env["history"]] == ["user", "assistant"]


def test_tool_call_reply_carries_model_content():
    env, _ = call_run(make_stub([tool_reply(content="Berikut ringkasannya.")], []))
    assert env["type"] == "function_call"
    assert env["reply"] == "Berikut ringkasannya."


def test_first_tool_call_wins():
    first = {"function": {"name": "create_alokasi", "arguments": SAMPLE_ARGUMENTS}}
    second = {"function": {"name": "other", "arguments": "{}"}}
    reply = {"content": None, "tool_calls": [first, second]}
    env, _ = call_run(make_stub([reply], []))
    assert env["function_name"] == "create_alokasi"
    assert env["arguments"] == SAMPLE_ARGUMENTS


# --- FR-08: multi-row delivery (parallel calls per row) ---

ROW2_ARGUMENTS = (
    '{"nama_karyawan":"Budi Santoso","nama_proyek":"OPRS Divisi WIN 2026",'
    '"tanggal":"2026-09-30","jenis_pekerjaan":"Testing sistem",'
    '"jam_mulai":"16:30","jam_selesai":"17:00","review":"[1/1/0/2] Done"}'
)


def tool_reply_multi(arguments_list):
    return {
        "content": None,
        "tool_calls": [
            {
                "id": f"call_{i}",
                "type": "function",
                "function": {"name": "create_alokasi", "arguments": arguments},
            }
            for i, arguments in enumerate(arguments_list, start=1)
        ],
    }


def test_multiple_rows_produce_array_arguments():
    calls = []
    reply = tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])
    env, _ = call_run(make_stub([reply], calls))
    assert env["success"] is True
    assert env["type"] == "function_call"
    assert env["function_name"] == "create_alokasi"
    rows = json.loads(env["arguments"])
    assert len(rows) == 2
    assert rows[0]["nama_karyawan"] == "Imam Ihsani"
    assert rows[1]["nama_karyawan"] == "Budi Santoso"
    assert rows[1]["review"] == "[1/1/0/2] Done"
    assert len(calls) == 1


def test_single_row_stays_object_string():
    calls = []
    env, _ = call_run(make_stub([tool_reply()], calls))
    assert json.loads(env["arguments"]) == json.loads(SAMPLE_ARGUMENTS)
    assert not env["arguments"].lstrip().startswith("[")


def test_mixed_multi_row_retries_then_returns_all_rows():
    calls = []
    stub = make_stub(
        [tool_reply_multi([SAMPLE_ARGUMENTS, INVALID_ARGUMENTS]),
         tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])],
        calls,
    )
    env, _ = call_run(stub)
    assert env["success"] is True
    rows = json.loads(env["arguments"])
    assert len(rows) == 2
    assert len(calls) == 2
    tool_msgs = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert tool_msgs[0]["content"] == "OK"
    assert "tanggal" in tool_msgs[1]["content"]


def test_multi_row_invalid_twice_returns_error_envelope():
    calls = []
    stub = make_stub(
        [tool_reply_multi([INVALID_ARGUMENTS, INVALID_ARGUMENTS]),
         tool_reply_multi([INVALID_ARGUMENTS, INVALID_ARGUMENTS])],
        calls,
    )
    env, _ = call_run(stub)
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["function_name"] == ""
    assert env["arguments"] == ""
    assert env["reply"].startswith("Data tidak valid setelah dicoba ulang")
    assert len(calls) == 2


def test_text_reply_with_none_content_normalizes_history():
    env, history = call_run(make_stub([text_reply(None)], []))
    assert env["reply"] is None
    assert history[1] == {"role": "assistant", "content": ""}


def test_system_prompt_carries_injected_context():
    calls = []
    call_run(make_stub([text_reply("ok")], calls))
    system = calls[0]["messages"][0]
    assert system["role"] == "system"
    assert "Rabu, 30 September 2026, 14:05 WIB" in system["content"]
    assert f"Logged-in user: {USER}" in system["content"]
    assert "Valid employees: Imam Ihsani, Budi Santoso" in system["content"]


def test_tools_attached_match_contract():
    calls = []
    call_run(make_stub([text_reply("ok")], calls))
    assert calls[0]["tools"] == to_openai_tools(CREATE_ALOKASI_TOOL)


def test_history_defaults_are_independent():
    calls = []
    complete = make_stub([text_reply("a"), text_reply("b")], calls)
    _, hist1 = call_run(complete)
    _, hist2 = call_run(complete, raw_message="second")
    assert len(hist1) == 2
    assert len(hist2) == 2
    assert hist1 is not hist2


# --- FR-05: validation, retry, fallback ---

INVALID_ARGUMENTS = '{"tanggal":"2026-13-45"}'


def test_valid_tool_call_does_not_retry():
    calls = []
    env, _ = call_run(make_stub([tool_reply()], calls))
    assert env["type"] == "function_call"
    assert len(calls) == 1


def test_invalid_tool_call_retries_once_with_errors():
    calls = []
    stub = make_stub([tool_reply(arguments=INVALID_ARGUMENTS), tool_reply()], calls)
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert env["success"] is True
    assert env["arguments"] == SAMPLE_ARGUMENTS
    assert len(calls) == 2

    sent = calls[1]["messages"]
    assert sent[-2]["role"] == "assistant"
    assert sent[-2]["tool_calls"][0]["id"] == "call_1"
    assert sent[-1]["role"] == "tool"
    assert sent[-1]["tool_call_id"] == "call_1"
    assert "tanggal" in sent[-1]["content"]
    assert "jam_selesai" in sent[-1]["content"]


def test_invalid_twice_returns_error_envelope():
    calls = []
    stub = make_stub(
        [tool_reply(arguments=INVALID_ARGUMENTS), tool_reply(arguments=INVALID_ARGUMENTS)],
        calls,
    )
    env, history = call_run(stub)
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["function_name"] == ""
    assert env["arguments"] == ""
    assert env["reply"].startswith("Data tidak valid setelah dicoba ulang")
    assert env["raw_message"] == EXAMPLE_MESSAGE
    assert len(calls) == 2
    assert history[1] == {"role": "assistant", "content": env["reply"]}
    assert env["history"] == history


def test_invalid_then_text_reply_is_normal_text():
    calls = []
    stub = make_stub(
        [tool_reply(arguments=INVALID_ARGUMENTS), text_reply("Lengkapi datanya dulu.")],
        calls,
    )
    env, _ = call_run(stub)
    assert env["success"] is True
    assert env["type"] == "text"
    assert env["reply"] == "Lengkapi datanya dulu."


# --- FR-07: clarification loop ---

PARTIAL_MESSAGE = "besok aku ngerjain modul PPN jam 1 sampai jam 4"


def test_partial_message_then_answer_produces_complete_call():
    question = "Untuk proyek apa alokasi ini?"
    calls1 = []
    env1, history1 = call_run(
        make_stub([text_reply(question)], calls1), raw_message=PARTIAL_MESSAGE
    )
    assert env1["type"] == "text"
    assert env1["reply"] == question

    answer = "OPRS Divisi WIN 2026"
    calls2 = []
    env2, history2 = call_run(
        make_stub([tool_reply()], calls2),
        raw_message=answer,
        history=history1,
    )
    assert env2["type"] == "function_call"
    args = json.loads(env2["arguments"])
    for field in (
        "nama_karyawan",
        "nama_proyek",
        "tanggal",
        "jenis_pekerjaan",
        "jam_mulai",
        "jam_selesai",
    ):
        assert args[field]

    sent = calls2[0]["messages"]
    assert [turn["role"] for turn in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == PARTIAL_MESSAGE
    assert sent[2]["content"] == question
    assert sent[3]["content"] == answer
    assert [turn["role"] for turn in history2] == ["user", "assistant", "user", "assistant"]


# --- project list validation (server-fetched lists) ---

def test_unknown_project_becomes_question_not_call():
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "OPRS WIN")
    calls = []
    env, history = call_run(make_stub([tool_reply(arguments=args)], calls))
    assert env["success"] is True
    assert env["type"] == "text"
    assert env["function_name"] == ""
    assert env["arguments"] == ""
    assert 'Maksud kamu "OPRS WIN"?' in env["reply"]
    assert "OPRS Divisi WIN 2026" in env["reply"]
    assert len(calls) == 1  # list misses are not retried
    assert history[-1]["content"] == env["reply"]


def test_unknown_project_blocks_whole_batch():
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "Proyek Fiktif")
    calls = []
    env, _ = call_run(make_stub([tool_reply_multi([SAMPLE_ARGUMENTS, bad])], calls))
    assert env["type"] == "text"
    assert 'Maksud kamu "Proyek Fiktif"?' in env["reply"]
    assert len(calls) == 1


def test_project_match_ignores_case_and_padding():
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "  oprs divisi win 2026 ")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []))
    assert env["type"] == "function_call"


def test_empty_projects_list_skips_check():
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "Anything At All")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []), projects=[])
    assert env["type"] == "function_call"


def test_no_close_candidate_still_asks():
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "zzz qqq")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []))
    assert env["type"] == "text"
    assert 'Maksud kamu "zzz qqq"?' in env["reply"]
    assert "Kandidat:" not in env["reply"]
