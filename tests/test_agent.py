import json
from datetime import datetime, timezone

from alokasi_agent import run
from alokasi_agent.agent import _find_calls, _resolve_name
from alokasi_agent.llm import to_openai_tools
from alokasi_agent.schema import CREATE_ALOKASI_TOOL, FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL

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


def find_reply(tool_name, name, call_id="call_f1"):
    return {
        "content": None,
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {"name": tool_name, "arguments": json.dumps({"name": name})},
            }
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


def test_system_prompt_never_carries_the_lists():
    calls = []
    call_run(make_stub([text_reply("ok")], calls))
    system = calls[0]["messages"][0]
    assert system["role"] == "system"
    assert "Rabu, 30 September 2026, 14:05 WIB" in system["content"]
    assert f"Logged-in user: {USER}" in system["content"]
    assert "Valid employees" not in system["content"]
    assert "Valid projects" not in system["content"]


def test_tools_attached_match_contract():
    calls = []
    call_run(make_stub([text_reply("ok")], calls))
    assert calls[0]["tools"] == to_openai_tools(
        CREATE_ALOKASI_TOOL, FIND_EMPLOYEE_TOOL, FIND_PROJECT_TOOL
    )


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
    assert "jam_mulai" in sent[-1]["content"]


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


def test_null_optional_fields_are_accepted_and_stripped():
    args = json.loads(SAMPLE_ARGUMENTS)
    args["review"] = None
    args["tim_pekerjaan"] = None
    calls = []
    stub = make_stub(
        [tool_reply(arguments=json.dumps(args)),
         tool_reply()],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    final = json.loads(env["arguments"])
    assert "review" not in final
    assert "tim_pekerjaan" not in final
    assert final["nama_karyawan"] == "Imam Ihsani"
    # One round only: an explicit null is absent, not an FR-05 error.
    assert len(calls) == 1


# --- project list validation (server-fetched lists) ---

def test_project_match_ignores_case_and_padding():
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "  oprs divisi win 2026 ")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []))
    assert env["type"] == "function_call"


def test_empty_projects_list_blocks_call():
    # Fail-closed: no list to check against means the name cannot be verified.
    args = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "Anything At All")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []), projects=[])
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["arguments"] == ""
    assert env["reply"] == "Daftar proyek tidak tersedia, coba lagi."


def test_post_retry_invalid_json_still_refuses():
    calls = []
    stub = make_stub(
        [tool_reply(arguments=INVALID_ARGUMENTS), tool_reply(arguments="not json")],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "error"
    assert env["reply"].startswith("Data tidak valid setelah dicoba ulang:")
    assert len(calls) == 2


# --- membership now redirects to find_* (fail closed) ---

def test_unknown_project_redirects_to_find_project():
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "OPRS WIN")
    calls = []
    stub = make_stub(
        [tool_reply(arguments=bad),
         find_reply("find_project", "OPRS WIN"),
         tool_reply()],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert env["arguments"] == SAMPLE_ARGUMENTS
    assert len(calls) == 3
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert 'Proyek "OPRS WIN" belum dipastikan.' in round2_tools[0]["content"]
    assert "find_project" in round2_tools[0]["content"]
    round3_tools = [m for m in calls[2]["messages"] if m["role"] == "tool"]
    assert round3_tools[-1]["content"] == (
        'No exact match for "OPRS WIN". Closest: OPRS Divisi WIN 2026. '
        "Ask the user which one is meant."
    )


def test_unknown_project_blocks_whole_batch():
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "Proyek Fiktif")
    calls = []
    stub = make_stub(
        [tool_reply_multi([SAMPLE_ARGUMENTS, bad]),
         find_reply("find_project", "Proyek Fiktif"),
         tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert round2_tools[0]["content"] == "OK"
    assert 'Proyek "Proyek Fiktif" belum dipastikan.' in round2_tools[1]["content"]


def test_no_close_candidate_ends_in_model_question():
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "zzz qqq")
    calls = []
    stub = make_stub(
        [tool_reply(arguments=bad),
         find_reply("find_project", "zzz qqq"),
         text_reply('Proyek "zzz qqq" nggak ada. Proyeknya yang mana?')],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "text"
    assert env["reply"] == 'Proyek "zzz qqq" nggak ada. Proyeknya yang mana?'
    round3_tools = [m for m in calls[2]["messages"] if m["role"] == "tool"]
    assert round3_tools[-1]["content"] == (
        '"zzz qqq" not found in the project list. Ask the user to check the spelling.'
    )


def test_unknown_employee_redirects_to_find_employee():
    bad = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "Imam")
    calls = []
    stub = make_stub(
        [tool_reply(arguments=bad),
         find_reply("find_employee", "Imam"),
         tool_reply()],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert env["arguments"] == SAMPLE_ARGUMENTS
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert 'Karyawan "Imam" belum dipastikan.' in round2_tools[0]["content"]
    assert "find_employee" in round2_tools[0]["content"]


def test_unknown_employee_blocks_whole_batch():
    bad = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "Karyawan Fiktif")
    calls = []
    stub = make_stub(
        [tool_reply_multi([SAMPLE_ARGUMENTS, bad]),
         find_reply("find_employee", "Karyawan Fiktif"),
         tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert 'Karyawan "Karyawan Fiktif" belum dipastikan.' in round2_tools[1]["content"]


def test_unknown_employee_no_close_candidate_ends_in_model_question():
    bad = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "zzz qqq")
    calls = []
    stub = make_stub(
        [tool_reply(arguments=bad),
         find_reply("find_employee", "zzz qqq"),
         text_reply('Karyawan "zzz qqq" nggak ada di daftar. Siapa namanya?')],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "text"
    assert env["reply"] == 'Karyawan "zzz qqq" nggak ada di daftar. Siapa namanya?'


def test_redirect_budget_exhaustion_refuses():
    bad = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "Karyawan Fiktif")
    calls = []
    stub = make_stub([tool_reply(arguments=bad)] * 3, calls)
    env, _ = call_run(stub)
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["arguments"] == ""
    assert "Tidak ada data yang dikirim" in env["reply"]
    assert len(calls) == 3


def test_max_rounds_exhaustion_refuses():
    calls = []
    stub = make_stub(
        [find_reply("find_employee", "Imam Ihsani", call_id=f"call_f{i}") for i in range(6)],
        calls,
    )
    env, _ = call_run(stub)
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["arguments"] == ""
    assert "Percobaan terlalu banyak tanpa hasil" in env["reply"]
    assert len(calls) == 6


def test_find_and_create_in_same_turn_replies_to_all():
    mixed = {
        "content": None,
        "tool_calls": [
            {
                "id": "call_f1",
                "type": "function",
                "function": {
                    "name": "find_project",
                    "arguments": json.dumps({"name": "oprs divisi win 2026"}),
                },
            },
            {"id": "call_1", "type": "function",
             "function": {"name": "create_alokasi", "arguments": SAMPLE_ARGUMENTS}},
        ],
    }
    calls = []
    stub = make_stub([mixed, tool_reply()], calls)
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert len(calls) == 2
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in round2_tools] == ["call_f1", "call_1"]
    assert round2_tools[0]["content"] == "Matched: OPRS Divisi WIN 2026"
    assert round2_tools[1]["content"] == "OK"


def test_find_employee_with_empty_list_reports_unavailable():
    calls = []
    stub = make_stub(
        [find_reply("find_employee", "Anyone"), text_reply("Daftar belum siap, coba lagi.")],
        calls,
    )
    env, _ = call_run(stub, employees=[])
    assert env["type"] == "text"
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert round2_tools[0]["content"] == "The employee list is unavailable, try again later."


# --- employee list validation (server-fetched lists) ---

def test_employee_match_ignores_case_and_padding():
    args = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "  imam ihsani ")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []))
    assert env["type"] == "function_call"


def test_empty_employees_list_blocks_call():
    # Fail-closed: no list to check against means the name cannot be verified.
    args = SAMPLE_ARGUMENTS.replace("Imam Ihsani", "Anyone At All")
    env, _ = call_run(make_stub([tool_reply(arguments=args)], []), employees=[])
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["arguments"] == ""
    assert env["reply"] == "Daftar karyawan tidak tersedia, coba lagi."


# --- membership checks: fail-closed lists, tim_pekerjaan, canonical rewrite ---

def with_tim(tim_value):
    row = json.loads(SAMPLE_ARGUMENTS)
    row["tim_pekerjaan"] = tim_value
    return json.dumps(row, separators=(",", ":"))


def test_both_empty_lists_block_call():
    env, _ = call_run(
        make_stub([tool_reply()], []), employees=[], projects=[]
    )
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["reply"] == "Daftar karyawan dan proyek tidak tersedia, coba lagi."


def test_empty_lists_still_pass_text_reply():
    env, _ = call_run(
        make_stub([text_reply("Untuk proyek apa alokasi ini?")], []),
        employees=[],
        projects=[],
    )
    assert env["success"] is True
    assert env["type"] == "text"
    assert env["reply"] == "Untuk proyek apa alokasi ini?"


def test_unknown_tim_member_redirects_to_find_employee():
    calls = []
    stub = make_stub(
        [tool_reply(arguments=with_tim("Orang Asing")),
         find_reply("find_employee", "Orang Asing"),
         tool_reply(arguments=with_tim("Budi Santoso"))],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert json.loads(env["arguments"])["tim_pekerjaan"] == "Budi Santoso"
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert 'Anggota tim "Orang Asing" belum dipastikan.' in round2_tools[0]["content"]
    assert "find_employee" in round2_tools[0]["content"]
    assert "minta user menghapusnya dari tim" in round2_tools[0]["content"]


def test_unknown_tim_member_blocks_whole_batch():
    good = SAMPLE_ARGUMENTS
    bad = with_tim("Orang Asing")
    calls = []
    stub = make_stub(
        [tool_reply_multi([good, bad]),
         find_reply("find_employee", "Orang Asing"),
         tool_reply_multi([good, with_tim("Budi Santoso")])],
        calls,
    )
    env, _ = call_run(stub)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2


def test_valid_tim_member_passes_through():
    env, _ = call_run(make_stub([tool_reply(arguments=with_tim("Budi Santoso"))], []))
    assert env["type"] == "function_call"
    assert json.loads(env["arguments"])["tim_pekerjaan"] == "Budi Santoso"


def test_case_mismatch_rewritten_to_canonical():
    row = json.loads(SAMPLE_ARGUMENTS)
    row["nama_karyawan"] = "  imam ihsani "
    row["nama_proyek"] = "oprs divisi win 2026"
    row["tim_pekerjaan"] = "budi santoso, IMAM IHSANI"
    env, _ = call_run(make_stub([tool_reply(arguments=json.dumps(row))], []))
    assert env["type"] == "function_call"
    args = json.loads(env["arguments"])
    assert args["nama_karyawan"] == "Imam Ihsani"
    assert args["nama_proyek"] == "OPRS Divisi WIN 2026"
    assert args["tim_pekerjaan"] == "Budi Santoso, Imam Ihsani"


# --- FR-08 row guard: what is inserted must equal what was confirmed ---

TWO_ROW_SUMMARY = (
    "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN"
    " | 09:00-12:00\n"
    "Budi Santoso | OPRS Divisi WIN 2026 | 2026-09-30 | Testing sistem"
    " | 16:30-17:00 | [1/1/0/2] Done. Benar?"
)
PENDING_HISTORY = [
    {"role": "user", "content": "pagi dev PPN, siang testing proyek OPRS"},
    {"role": "assistant", "content": TWO_ROW_SUMMARY},
]
# Same as ROW2_ARGUMENTS but jam_mulai drifted to 16:00 — valid JSON and
# valid format, so FR-05 never sees it; only the row guard can catch it.
DRIFTED_ROW2_ARGUMENTS = (
    '{"nama_karyawan":"Budi Santoso","nama_proyek":"OPRS Divisi WIN 2026",'
    '"tanggal":"2026-09-30","jenis_pekerjaan":"Testing sistem",'
    '"jam_mulai":"16:00","jam_selesai":"17:00","review":"[1/1/0/2] Done"}'
)


def test_confirmed_rows_parses_last_assistant_summary():
    from alokasi_agent.agent import _confirmed_rows

    rows = _confirmed_rows(PENDING_HISTORY)
    assert rows == [
        {
            "nama_karyawan": "Imam Ihsani",
            "nama_proyek": "OPRS Divisi WIN 2026",
            "tanggal": "2026-09-29",
            "jenis_pekerjaan": "Development Modul PPN",
            "jam_mulai": "09:00",
            "jam_selesai": "12:00",
        },
        {
            "nama_karyawan": "Budi Santoso",
            "nama_proyek": "OPRS Divisi WIN 2026",
            "tanggal": "2026-09-30",
            "jenis_pekerjaan": "Testing sistem",
            "jam_mulai": "16:30",
            "jam_selesai": "17:00",
            "review": "[1/1/0/2] Done",
        },
    ]
    assert _confirmed_rows([]) == []
    assert _confirmed_rows([{"role": "assistant", "content": "Untuk proyek apa?"}]) == []
    assert _confirmed_rows([{"role": "user", "content": "a | b | c | d | e"}]) == []


def test_row_guard_matching_rows_pass_without_nudge():
    calls = []
    stub = make_stub([tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])], calls)
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    assert len(calls) == 1  # exact match -> no corrective retry


ONE_ROW_SUMMARY = (
    "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN"
    " | 09:00-12:00. Benar?"
)
PENDING_HISTORY_ONE_ROW = [
    {"role": "user", "content": "isi dev PPN OPRS"},
    {"role": "assistant", "content": ONE_ROW_SUMMARY},
]


def test_row_guard_null_optionals_match_summary_without_keys():
    # Null optional keys count as absent: the call equals the confirmed row,
    # so it is accepted in one round (no nudge, no refusal).
    args = json.loads(SAMPLE_ARGUMENTS)
    args["review"] = None
    args["tim_pekerjaan"] = None
    calls = []
    stub = make_stub(
        [tool_reply(arguments=json.dumps(args)),
         tool_reply(arguments=json.dumps(args))],
        calls,
    )
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY_ONE_ROW)
    assert env["type"] == "function_call"
    assert len(calls) == 1  # no nudge round
    final = json.loads(env["arguments"])
    assert "review" not in final
    assert "tim_pekerjaan" not in final
    assert final["nama_karyawan"] == "Imam Ihsani"


def test_row_guard_mismatch_nudges_with_confirmed_rows():
    calls = []
    stub = make_stub(
        [tool_reply(), tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS])],
        calls,
    )
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    assert len(calls) == 2
    nudge = calls[1]["messages"][-1]
    assert nudge["role"] == "user"
    assert "2 baris" in nudge["content"]
    assert "Testing sistem" in nudge["content"]  # the nudge carries the actual rows


def test_row_guard_still_mismatched_refuses():
    calls = []
    stub = make_stub([tool_reply(), tool_reply()], calls)
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["success"] is False
    assert env["type"] == "error"
    assert env["function_name"] == ""
    assert env["arguments"] == ""
    assert "1 panggilan vs 2 baris" in env["reply"]
    assert "Tidak ada data yang dikirim" in env["reply"]
    assert len(calls) == 2
    assert env["history"][-1] == {"role": "assistant", "content": env["reply"]}


def test_row_guard_extra_call_refuses():
    calls = []
    three = tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS, SAMPLE_ARGUMENTS])
    stub = make_stub([three, three], calls)
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "error"
    assert "3 panggilan vs 2 baris" in env["reply"]
    assert len(calls) == 2


def test_row_guard_field_drift_recovers_after_nudge():
    # Two rows, right count, but row 2's jam_mulai drifted from 16:30 to
    # 16:00. Format-valid, so only equality against the confirmed summary
    # can catch it.
    calls = []
    stub = make_stub(
        [
            tool_reply_multi([SAMPLE_ARGUMENTS, DRIFTED_ROW2_ARGUMENTS]),
            tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS]),
        ],
        calls,
    )
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "function_call"
    rows = json.loads(env["arguments"])
    assert len(rows) == 2
    assert rows[1]["jam_mulai"] == "16:30"
    assert len(calls) == 2


def test_row_guard_fr05_shrink_recovered():
    # FR-05 retry clears its errors but drops a row; the row guard must
    # still recover the confirmed batch.
    calls = []
    stub = make_stub(
        [
            tool_reply_multi([SAMPLE_ARGUMENTS, INVALID_ARGUMENTS]),  # FR-05 retry
            tool_reply(),                                             # shrinks to 1
            tool_reply_multi([SAMPLE_ARGUMENTS, ROW2_ARGUMENTS]),     # nudge recovers
        ],
        calls,
    )
    env, _ = call_run(stub, raw_message="ya", history=PENDING_HISTORY)
    assert env["type"] == "function_call"
    assert len(json.loads(env["arguments"])) == 2
    assert len(calls) == 3


# --- find_* name resolution (difflib, no LLM) ---

def test_resolve_name_exact_match_returns_canonical_spelling():
    assert _resolve_name("imam ihsani", "find_employee", EMPLOYEES) == "Matched: Imam Ihsani"


def test_resolve_name_returns_candidates_for_near_match():
    result = _resolve_name("Imam", "find_employee", ["Imam Ihsani", "Imam Hidayat"])
    assert result.startswith('No exact match for "Imam". Closest: ')
    assert "Imam Ihsani" in result and "Imam Hidayat" in result
    assert result.endswith("Ask the user which one is meant.")


def test_resolve_name_not_found():
    assert _resolve_name("zzz qqq", "find_project", PROJECTS) == (
        '"zzz qqq" not found in the project list. Ask the user to check the spelling.'
    )


def test_resolve_name_empty_list_is_unavailable():
    assert _resolve_name("Anyone", "find_employee", []) == (
        "The employee list is unavailable, try again later."
    )


def test_resolve_name_unreadable_name_asks_to_retry():
    assert _resolve_name("", "find_employee", EMPLOYEES) == (
        'Could not read the name. Call again with {"name": "..."} as plain text.'
    )


def test_find_call_with_bad_json_reads_as_empty_name():
    message = {
        "tool_calls": [
            {
                "id": "call_x",
                "type": "function",
                "function": {"name": "find_employee", "arguments": "not json"},
            }
        ]
    }
    assert _find_calls(message) == [("call_x", "find_employee", "")]


# --- realistic made-up project list (stand-in for the unfetchable MIS list) ---
# Siblings share long prefixes (OPRS Divisi ..., "Managed Service - ...",
# "... Tahap N"), so the tests below only pass when the COMPLETE name is
# compared — a lookup using the first few characters could not tell them apart.

REAL_PROJECTS = [
    "OPRS Divisi FIN 2026",
    "OPRS Divisi HRD 2026",
    "OPRS Divisi IT 2026",
    "OPRS Divisi WIN 2026",
    "Managed Service - Instalasi IKR Area Depok Periode September 2026",
    "Managed Service - Instalasi IKR Area Bekasi Periode September 2026",
    "Relokasi FO Ruas Jalan BII Bandung Tahap 3",
    "Relokasi FO Ruas Jalan BII Bandung Tahap 4",
]


def test_full_project_names_resolve_to_their_own_sibling():
    # Each complete name matches its own spelling, never a same-prefix sibling.
    for name in REAL_PROJECTS:
        assert _resolve_name(name, "find_project", REAL_PROJECTS) == f"Matched: {name}"


def test_full_project_name_match_ignores_case_and_padding():
    assert (
        _resolve_name("  oprs divisi win 2026 ", "find_project", REAL_PROJECTS)
        == "Matched: OPRS Divisi WIN 2026"
    )
    assert (
        _resolve_name(
            "relokasi fo ruas jalan bii bandung tahap 4", "find_project", REAL_PROJECTS
        )
        == "Matched: Relokasi FO Ruas Jalan BII Bandung Tahap 4"
    )


def test_oprs_abbreviation_returns_sibling_candidates():
    # Regression pin for the reported bug: "OPRS <div>" shorthand scores
    # 0.571 against the full name — below cutoff 0.6 it used to come back
    # "not found" with no candidates at all.
    assert _resolve_name("OPRS WIN", "find_project", REAL_PROJECTS) == (
        'No exact match for "OPRS WIN". '
        "Closest: OPRS Divisi WIN 2026, OPRS Divisi FIN 2026. "
        "Ask the user which one is meant."
    )
    assert _resolve_name("OPRS HRD", "find_project", REAL_PROJECTS) == (
        'No exact match for "OPRS HRD". '
        "Closest: OPRS Divisi HRD 2026. "
        "Ask the user which one is meant."
    )


def test_near_full_variants_return_the_right_candidates():
    # One word missing from an otherwise complete name must still surface
    # the official spelling for the model to offer.
    result = _resolve_name("OPRS WIN 2026", "find_project", REAL_PROJECTS)
    assert result.startswith('No exact match for "OPRS WIN 2026". Closest: ')
    assert "OPRS Divisi WIN 2026" in result

    result = _resolve_name(
        "Managed Service - Instalasi IKR Area Depok", "find_project", REAL_PROJECTS
    )
    assert "Managed Service - Instalasi IKR Area Depok Periode September 2026" in result

    result = _resolve_name(
        "Relokasi FO Jalan BII Bandung Tahap 3", "find_project", REAL_PROJECTS
    )
    assert "Relokasi FO Ruas Jalan BII Bandung Tahap 3" in result


def test_prefix_only_input_never_validates_as_a_name():
    # First few words can never come back "Matched" — candidates or
    # not-found only, so a prefix never passes as a project name.
    for prefix in ("OPRS", "OPRS Div", "Managed Service -", "Relokasi FO Ruas"):
        result = _resolve_name(prefix, "find_project", REAL_PROJECTS)
        assert not result.startswith("Matched:"), result


def test_full_project_name_accepted_in_one_round():
    # create_alokasi carrying a complete in-list name needs no redirect.
    calls = []
    env, _ = call_run(make_stub([tool_reply()], calls), projects=REAL_PROJECTS)
    assert env["type"] == "function_call"
    assert json.loads(env["arguments"])["nama_proyek"] == "OPRS Divisi WIN 2026"
    assert len(calls) == 1


def test_oprs_abbreviation_flow_shows_candidates_then_corrects():
    # End-to-end: model first sends "OPRS HRD" -> redirected to find_project
    # -> tool answers with the sibling candidates -> model corrects to the
    # full list spelling and the row is accepted.
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "OPRS HRD")
    fixed = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "OPRS Divisi HRD 2026")
    calls = []
    stub = make_stub(
        [
            tool_reply(arguments=bad),
            find_reply("find_project", "OPRS HRD"),
            tool_reply(arguments=fixed),
        ],
        calls,
    )
    env, _ = call_run(stub, projects=REAL_PROJECTS)
    assert env["type"] == "function_call"
    assert json.loads(env["arguments"])["nama_proyek"] == "OPRS Divisi HRD 2026"
    round3_tools = [m for m in calls[2]["messages"] if m["role"] == "tool"]
    assert round3_tools[-1]["content"] == (
        'No exact match for "OPRS HRD". Closest: OPRS Divisi HRD 2026. '
        "Ask the user which one is meant."
    )


def test_prefix_in_create_alokasi_is_redirected_to_find_project():
    # The membership gate is whole-string: a prefix of a valid name is not
    # a member, so the row never reaches the ERP unchecked.
    bad = SAMPLE_ARGUMENTS.replace("OPRS Divisi WIN 2026", "OPRS Div")
    calls = []
    stub = make_stub(
        [
            tool_reply(arguments=bad),
            find_reply("find_project", "OPRS Div"),
            tool_reply(),
        ],
        calls,
    )
    env, _ = call_run(stub, projects=REAL_PROJECTS)
    assert env["type"] == "function_call"
    round2_tools = [m for m in calls[1]["messages"] if m["role"] == "tool"]
    assert 'Proyek "OPRS Div" belum dipastikan.' in round2_tools[0]["content"]
    assert "find_project" in round2_tools[0]["content"]
