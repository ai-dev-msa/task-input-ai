from datetime import datetime, timedelta, timezone

from alokasi_agent.prompt import PROMPT_TEMPLATE, build_system_prompt

EMPLOYEES = ["Imam Ihsani", "Budi Santoso"]
PROJECTS = ["OPRS Divisi WIN 2026"]
USER = "Andi Wijaya"


def build(now: datetime) -> str:
    return build_system_prompt(now, USER, EMPLOYEES, PROJECTS)


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


def test_context_values_rendered():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert f"Logged-in user: {USER}" in out
    assert "Valid employees: Imam Ihsani, Budi Santoso" in out
    assert "Valid projects: OPRS Divisi WIN 2026" in out


def test_rule_markers_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "If no date is given, ask." in out
    assert "use today" not in out
    assert "except tanggal" not in out
    assert "The function requires every field" in out
    assert "accepts null" not in out
    assert "Setelah memanggil fungsi, berhenti." in out
    assert "After the function returns" not in out
    assert "create_alokasi" in out
    assert "Benar?" in out
    assert "MSA AI Assistant (MITA)" in out
    assert "PT Mitra Sinergi Adhitama (MSA)" in out
    # FR-06 prompt coverage (see docs/superpowers/specs/2026-10-01-fr06-prompt-coverage-design.md)
    assert '"29 September 2026" become 2026-09-29' in out
    assert "If no year is given, use the current year." in out
    assert '"09.00" means the same as "09:00"' in out
    assert 'A range like "09:00-12:00" is' in out
    # FR-07: missing/ambiguous fields -> one clarifying question, no call
    assert "ask one short clarifying question" in out
    assert "Do not call the function." in out
    # FR-10: confirmation gate — cancel without calling, edits re-show the summary
    assert '"batal"' in out
    assert "Wait for the next message." in out
    assert '"ganti jam selesai jadi 13:00"' in out
    assert "show the full summary line again with the new value" in out


def test_multi_record_rule_kept():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "(For several records, one line each.)" in out


def test_optional_field_rules_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "Plus two optional fields" in out
    assert "review (optional)" in out
    assert "tim_pekerjaan (optional)" in out
    assert '"[a/b/c/d] status"' in out
    assert "the work name goes to jenis_pekerjaan" in out
    assert "max 3 days after the task date" in out
    assert "Do not ask the user about it." in out
    assert "omitted when the user gave none" in out
    assert "character-for-character in the valid" in out
    assert 'Add " | review"' in out


def test_multi_row_rules_present():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "call it once per row" in out
    assert "all calls\n   in the same reply" in out
    assert "independently from the current WIB date" in out
    assert "two `create_alokasi` calls in the same reply" in out
    assert "Dimas Eka Priyadi | OPRS Divisi WIN 2026 | 2026-09-30" in out


def test_non_utc_aware_datetime():
    plus_five_half = timezone(timedelta(hours=5, minutes=30))
    out = build(datetime(2026, 9, 30, 6, 5, tzinfo=plus_five_half))
    assert "Rabu, 30 September 2026, 07:35 WIB" in out


def test_placeholder_in_value_not_reexpanded():
    out = build_system_prompt(
        datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc),
        "{{employee_list}}",
        EMPLOYEES,
        PROJECTS,
    )
    assert "Logged-in user: {{employee_list}}" in out
    assert "Logged-in user: Imam Ihsani" not in out


def test_template_contains_all_placeholders():
    for token in ("{{now_wib}}", "{{current_user_name}}", "{{employee_list}}", "{{project_list}}"):
        assert token in PROMPT_TEMPLATE
