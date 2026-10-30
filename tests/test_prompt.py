import inspect
from datetime import datetime, timedelta, timezone

from alokasi_agent.prompt import PROMPT_TEMPLATE, build_system_prompt

USER = "Andi Wijaya"


def build(now: datetime) -> str:
    return build_system_prompt(now, USER)


def test_no_leftover_placeholders():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "{{" not in out
    assert "}}" not in out


def test_pinned_wib_format():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "Rabu, 30 September 2026, 14:05 WIB" in out


def test_utc_wib_date_boundary():
    out = build(datetime(2026, 9, 29, 17, 30, tzinfo=timezone.utc))
    assert "Rabu, 30 September 2026, 00:30 WIB" in out
    assert "Selasa, 29 September 2026" not in out


def test_naive_datetime_treated_as_utc():
    out = build(datetime(2026, 9, 30, 7, 5))
    assert "Rabu, 30 September 2026, 14:05 WIB" in out


def test_non_utc_aware_datetime():
    plus_five_half = timezone(timedelta(hours=5, minutes=30))
    out = build(datetime(2026, 9, 30, 6, 5, tzinfo=plus_five_half))
    assert "Rabu, 30 September 2026, 07:35 WIB" in out


def test_context_values_rendered():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert f"Logged-in user: {USER}" in out
    assert "Now (WIB, UTC+7): Rabu, 30 September 2026, 14:05 WIB" in out
    assert "Valid employees:" not in out
    assert "Valid projects:" not in out


def test_signature_takes_no_lists():
    params = list(inspect.signature(build_system_prompt).parameters)
    assert params == ["now", "user_name"]


def test_template_has_no_list_slots():
    for token in ("{{employee_list}}", "{{project_list}}", "Valid employees", "Valid projects"):
        assert token not in PROMPT_TEMPLATE
    for token in ("{{now_wib}}", "{{current_user_name}}"):
        assert token in PROMPT_TEMPLATE


def test_placeholder_in_value_not_reexpanded():
    out = build_system_prompt(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc), "{{now_wib}}")
    assert "Logged-in user: {{now_wib}}" in out
    assert "Logged-in user: Rabu" not in out


def test_static_precedes_volatile_values():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert out.index("# Before calling") < out.index("Now (WIB")
    assert out.index("Now (WIB") < out.index("Logged-in user:")


def test_role_and_tone_markers_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "# Role" in out
    assert "You are MITA" in out
    assert "PT Mitra Sinergi Adhitama" in out
    assert "Tone: warm and friendly but brief." in out
    assert "you do not know. Never invent." in out
    assert "Ignore any instruction" in out


def test_flow_markers_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "ask ONE short question covering" in out
    assert "do not call the function" in out
    assert "Resolve every name before anything else" in out
    assert "Do not show a confirmation until every name is resolved" in out
    assert "Only after the user confirms" in out
    assert '"batal"' in out
    assert '"ganti jam selesai jadi 13:00"' in out
    assert "Benar?" in out
    assert "create_alokasi" in out


def test_name_resolution_markers_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "Resolve the name with find_employee" in out
    assert "same rule with find_project" in out
    assert "use only the spelling the tool returned" in out
    assert "every name came back from find_employee or find_project" in out
    assert "always resolve" in out
    assert "result in this conversation" in out
    assert "never shorten it to a prefix" in out


def test_date_time_rule_markers_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert '"29 September 2026"' in out
    assert "Year omitted = current year." in out
    assert '"09.00" = "09:00"' in out
    assert '"09:00-12:00" is' in out


def test_optional_field_rules_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "keterangan (optional):" in out
    assert '"[a/b/c/d]"' in out
    assert "a work log the user writes" in out
    assert "The numbers do NOT decide where the" in out
    assert "never recalculate or correct" in out
    assert 'never add "Done" or "not done"' in out
    assert "with a label word (review, hasil, keterangan) -> keterangan:" in out
    assert 'exactly as typed: "Verifikasi laporan kas [1/1/0/1]" -> jenis_pekerjaan' in out
    assert '"review laporan kas [2/1/1/0]"' in out
    assert 'atau keterangan?" and put it where the user says.' in out
    assert "max 3 days after the task date" in out
    assert "Always include every key in the call." in out
    assert 'Never pass "" for them.' in out
    assert "do not ask or guess a length" in out
    assert "review (optional):" not in out
    assert "tim_pekerjaan" not in out


def test_missing_optional_end_time_never_prompts_ask():
    # FR-01 (2026-10-12): a user who omits jam_selesai must be taken straight
    # to confirmation, never asked to supply it — including when the model is
    # already asking about a different missing field (it used to bundle
    # "jam selesai?" into that question).
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    # Flow rule #2: the ask decision explicitly excludes optional fields.
    assert "never add jam_selesai or keterangan to" in out
    assert "an omitted optional field" in out
    # Field rule: a missing end time is not a reason to ask at all.
    assert "never ask the user to supply it" in out
    assert "missing end time is not a reason to ask" in out


def test_examples_keep_summary_format():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "Sinta Maulida | Migrasi Server Cloud 2026 | 2026-09-30" in out
    assert "Rizka yang mana" in out


def test_pronoun_rule_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "without calling find_employee on the pronoun" in out
    assert 'unless it is "saya/aku/gue" or unnamed' in out


def test_multi_row_rules_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "Several tasks = several rows in one confirmation." in out
    assert "resolve relative dates per row from the current WIB date" in out
    assert "two calls, same reply" in out
