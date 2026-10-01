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


def test_multi_record_rule_kept():
    out = build(datetime(2026, 9, 30, 7, 5, tzinfo=timezone.utc))
    assert "(For several records, one line each.)" in out


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
