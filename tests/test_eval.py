import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from alokasi_agent.eval import (
    aggregate,
    classify,
    load_cases,
    load_fixture,
    parse_summary,
    score_turn,
)

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "eval" / "cases.jsonl"
FIXTURE_PATH = ROOT / "eval" / "fixtures" / "v1.json"

ROW = {
    "nama_karyawan": "Imam Ihsani",
    "nama_proyek": "OPRS Divisi WIN 2026",
    "tanggal": "2026-09-29",
    "jenis_pekerjaan": "Development Modul PPN",
    "jam_mulai": "09:00",
    "jam_selesai": "12:00",
}
SUMMARY_LINE = (
    "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN "
    "| 09:00-12:00. Benar?"
)


def call_envelope(rows):
    """Envelope as run() builds it: one row -> object string, many -> array."""
    arguments = rows[0] if len(rows) == 1 else rows
    return {
        "success": True,
        "type": "function_call",
        "function_name": "create_alokasi",
        "arguments": json.dumps(arguments),
        "reply": None,
    }


def text_envelope(reply):
    return {"success": True, "type": "text", "function_name": "", "reply": reply}


# --- parse_summary ---


def test_parse_summary_single_row():
    assert parse_summary(SUMMARY_LINE) == [ROW]


def test_parse_summary_strips_confirmation_suffixes():
    bare = SUMMARY_LINE.replace(". Benar?", "")
    assert parse_summary(SUMMARY_LINE) == [ROW]
    assert parse_summary(SUMMARY_LINE.replace("Benar?", "Salah?")) == [ROW]
    assert parse_summary(bare + ".") == [ROW]  # trailing dot only
    assert parse_summary(bare + " Benar?") == [ROW]  # no dot before Benar?
    assert parse_summary(bare) == [ROW]  # nothing to strip


def test_parse_summary_keeps_review_and_tim():
    line = (
        "Ratna Kusumawati | Pengembangan Produk Baru 2026 | 2026-09-29 "
        "| ngerjain stress test aplikasi | 09:00-12:00 "
        "| [1/1/1/1] Done | Eko Prasetyo, Mega Puspita. Benar?"
    )
    rows = parse_summary(line)
    assert len(rows) == 1
    assert rows[0]["review"] == "[1/1/1/1] Done"
    assert rows[0]["tim_pekerjaan"] == "Eko Prasetyo, Mega Puspita"


def test_parse_summary_ignores_drop_review_notice():
    reply = (
        "Review hanya bisa diisi maksimal 3 hari setelah tanggal tugas.\n"
        "Eka Mulyani | Penjualan Korporat Wilayah Jabar 2026 | 2026-09-26 "
        "| bikin laporan kunjungan klien | 10:00-12:00. Benar?"
    )
    rows = parse_summary(reply)
    assert len(rows) == 1
    assert "review" not in rows[0]
    assert rows[0]["jam_mulai"] == "10:00"


def test_parse_summary_two_rows():
    reply = (
        "Rahma Aulia | Penjualan Korporat Wilayah Jabar 2026 | 2026-10-01 "
        "| bikin laporan penjualan | 09:00-11:00\n"
        "Rahma Aulia | Penjualan Korporat Wilayah Jabar 2026 | 2026-10-01 "
        "| follow up klien | 13:00-15:00. Benar?"
    )
    rows = parse_summary(reply)
    assert [row["jenis_pekerjaan"] for row in rows] == [
        "bikin laporan penjualan",
        "follow up klien",
    ]


def test_parse_summary_bad_date_returns_nothing():
    reply = SUMMARY_LINE.replace("2026-09-29", "29/09/2026")
    assert parse_summary(reply) == []


def test_parse_summary_bad_time_returns_nothing():
    assert parse_summary(SUMMARY_LINE.replace("09:00-12:00", "9:00-12:00")) == []
    assert parse_summary(SUMMARY_LINE.replace("09:00-12:00", "14.70-16.00")) == []


def test_parse_summary_empty_required_part_returns_nothing():
    assert parse_summary(SUMMARY_LINE.replace("Imam Ihsani", "")) == []


def test_parse_summary_too_many_parts_returns_nothing():
    assert parse_summary(SUMMARY_LINE.replace(". Benar?", " | a | b | c. Benar?")) == []


def test_parse_summary_empty_optional_part_is_dropped():
    line = SUMMARY_LINE.replace(". Benar?", " | . Benar?")
    assert parse_summary(line) == [ROW]


def test_parse_summary_no_summary():
    assert parse_summary("Untuk proyek apa alokasi ini?") == []
    assert parse_summary("") == []
    assert parse_summary(None) == []
    assert parse_summary("Review bisa diisi maks 3 hari.\nBenar?") == []


# --- classify ---


def test_classify_function_call_wins():
    envelope = call_envelope([ROW])
    envelope["reply"] = SUMMARY_LINE
    assert classify(envelope) == "call"


def test_classify_summary_is_confirm_even_with_question_mark():
    assert classify(text_envelope(SUMMARY_LINE)) == "confirm"


def test_classify_question_is_ask():
    assert classify(text_envelope("Untuk proyek apa alokasi ini?")) == "ask"


def test_classify_plain_text_is_other():
    assert classify(text_envelope("Oke, dibatalkan.")) == "other"


def test_classify_error_envelope_is_other():
    envelope = {
        "success": False,
        "type": "error",
        "reply": "Data tidak valid setelah dicoba ulang: tanggal tidak valid",
    }
    assert classify(envelope) == "other"


# --- score_turn ---


def test_score_confirm_with_matching_summary():
    score = score_turn({"kind": "confirm", "rows": [ROW]}, text_envelope(SUMMARY_LINE))
    assert score["expected"] == "confirm"
    assert score["predicted"] == "confirm"
    assert score["decision_correct"] is True
    assert score["row_exact"] is True
    assert score["field_correct"] == score["field_total"] == 6


def test_score_drop_review_counts_as_confirm():
    gold = {key: value for key, value in ROW.items() if key != "review"}
    expect = {"kind": "drop_review", "rows": [gold]}
    reply = (
        "Review hanya bisa diisi maksimal 3 hari setelah tanggal tugas.\n"
        "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN "
        "| 09:00-12:00. Benar?"
    )
    score = score_turn(expect, text_envelope(reply))
    assert score["decision_correct"] is True
    assert score["row_exact"] is True


def test_score_call_single_row_object_arguments():
    score = score_turn({"kind": "call", "calls": [ROW]}, call_envelope([ROW]))
    assert score["decision_correct"] is True
    assert score["row_exact"] is True


def test_score_call_multi_row_array_arguments():
    row2 = dict(ROW, nama_karyawan="Budi Santoso", jam_mulai="16:30", jam_selesai="17:00")
    score = score_turn({"kind": "call", "calls": [ROW, row2]}, call_envelope([ROW, row2]))
    assert score["decision_correct"] is True
    assert score["row_exact"] is True
    assert score["field_correct"] == score["field_total"] == 12


def test_score_phantom_empty_review_fails_exact_and_field():
    phantom = dict(ROW, review="")
    score = score_turn({"kind": "call", "calls": [ROW]}, call_envelope([phantom]))
    assert score["decision_correct"] is True  # class is right, row is not
    assert score["row_exact"] is False
    assert score["field_total"] == 7  # union of keys: 6 gold + phantom review
    assert score["field_correct"] == 6


def test_score_row_count_mismatch():
    row2 = dict(ROW, jenis_pekerjaan="Lain task", jam_mulai="13:00", jam_selesai="15:00")
    score = score_turn({"kind": "call", "calls": [ROW, row2]}, call_envelope([ROW]))
    assert score["row_exact"] is False
    assert score["field_total"] == 12  # row 2 has no counterpart: all 6 missing
    assert score["field_correct"] == 6


def test_score_ask_turn_has_no_row_metrics():
    expect = {"kind": "ask", "asks_about": ["tanggal"]}
    score = score_turn(expect, text_envelope("Tanggalnya kapan?"))
    assert score["decision_correct"] is True
    assert score["row_total"] == 0
    assert score["row_exact"] is None


def test_score_ask_vs_confirm_is_wrong():
    expect = {"kind": "ask", "asks_about": ["tanggal"]}
    score = score_turn(expect, text_envelope(SUMMARY_LINE))
    assert score["predicted"] == "confirm"
    assert score["decision_correct"] is False


def test_score_confirm_vs_ask_is_wrong_and_scores_zero_fields():
    score = score_turn({"kind": "confirm", "rows": [ROW]}, text_envelope("Tanggalnya kapan?"))
    assert score["predicted"] == "ask"
    assert score["decision_correct"] is False
    assert score["row_exact"] is False
    assert score["field_correct"] == 0
    assert score["field_total"] == 6


def test_score_optional_field_recall():
    gold = dict(ROW, review="[1/1/1/1] Done", tim_pekerjaan="Eko Prasetyo, Mega Puspita")
    expect = {"kind": "confirm", "rows": [gold]}
    missing = score_turn(expect, text_envelope(SUMMARY_LINE))
    assert missing["optional_total"] == 2
    assert missing["optional_correct"] == 0
    assert missing["row_exact"] is False

    line = (
        "Imam Ihsani | OPRS Divisi WIN 2026 | 2026-09-29 | Development Modul PPN "
        "| 09:00-12:00 | [1/1/1/1] Done | Eko Prasetyo, Mega Puspita. Benar?"
    )
    present = score_turn(expect, text_envelope(line))
    assert present["optional_correct"] == present["optional_total"] == 2
    assert present["row_exact"] is True


def test_score_cancel_and_refuse_are_other():
    cancel = score_turn({"kind": "cancel"}, text_envelope("Oke, dibatalkan."))
    assert cancel["decision_correct"] is True
    assert cancel["row_total"] == 0

    refuse = score_turn(
        {"kind": "refuse"},
        text_envelope("Maaf, saya hanya bisa membantu input alokasi tugas."),
    )
    assert refuse["decision_correct"] is True


# --- aggregate ---


def make_score(expected, predicted, **overrides):
    score = {
        "expected": expected,
        "predicted": predicted,
        "decision_correct": expected == predicted,
        "row_exact": None,
        "row_total": 0,
        "field_correct": 0,
        "field_total": 0,
        "optional_correct": 0,
        "optional_total": 0,
    }
    score.update(overrides)
    return score


def test_aggregate_decision_and_confusion_math():
    scores = [
        make_score("call", "call", category="a"),
        make_score("confirm", "ask", category="b"),
        make_score("ask", "ask", category="a"),
        make_score("other", "other", category="b"),
    ]
    metrics = aggregate(scores, api_errors=2)
    assert metrics["decision_correct"] == 3
    assert metrics["decision_total"] == 4
    assert metrics["decision_accuracy"] == 0.75
    assert metrics["confusion"]["confirm"]["ask"] == 1
    assert metrics["confusion"]["ask"]["ask"] == 1
    assert metrics["api_error_count"] == 2
    # two predicted asks (one right, one on a confirm turn)
    assert metrics["ask_predicted"] == 2
    assert metrics["ask_expected"] == 1
    assert metrics["ask_correct"] == 1
    assert metrics["ask_precision"] == 0.5
    assert metrics["ask_recall"] == 1.0


def test_aggregate_row_field_optional_math():
    scores = [
        make_score("confirm", "confirm", row_exact=True, row_total=1,
                   field_correct=6, field_total=6, optional_total=2,
                   optional_correct=1, category="x"),
        make_score("call", "call", row_exact=False, row_total=1,
                   field_correct=7, field_total=8, category="x"),
    ]
    metrics = aggregate(scores)
    assert metrics["row_exact"] == 1
    assert metrics["row_total"] == 2
    assert metrics["row_exact_rate"] == 0.5
    assert metrics["field_correct"] == 13
    assert metrics["field_total"] == 14
    assert metrics["field_accuracy"] == 13 / 14
    assert metrics["optional_field_recall"] == 0.5
    group = metrics["per_category"]["x"]
    assert group["decision_correct"] == 2 and group["decision_total"] == 2
    assert group["row_exact"] == 1 and group["row_total"] == 2


def test_aggregate_empty_is_none_not_crash():
    metrics = aggregate([])
    assert metrics["decision_accuracy"] is None
    assert metrics["ask_precision"] is None
    assert metrics["api_error_count"] == 0


# --- dataset integrity ---


def test_dataset_has_46_cases_with_unique_ids():
    cases = load_cases(CASES_PATH)
    assert len(cases) == 46
    assert len({case["id"] for case in cases}) == 46


def test_dataset_kind_and_split_counts():
    cases = load_cases(CASES_PATH)
    kinds = Counter(
        turn["expect"]["kind"] for case in cases for turn in case["turns"]
    )
    assert dict(kinds) == {
        "confirm": 35,
        "call": 33,
        "ask": 12,
        "drop_review": 1,
        "cancel": 1,
        "refuse": 1,
    }
    assert dict(Counter(case["split"] for case in cases)) == {"dev": 34, "test": 12}


def test_every_case_fixture_resolves():
    cases = load_cases(CASES_PATH)
    for case in cases:
        fixture = load_fixture(ROOT / "eval" / "fixtures" / f"{case['fixture']}.json")
        assert isinstance(fixture["employees"], list) and fixture["employees"]
        assert isinstance(fixture["projects"], list) and fixture["projects"]


def test_every_case_now_is_tz_aware():
    for case in load_cases(CASES_PATH):
        assert datetime.fromisoformat(case["now"]).tzinfo is not None


def test_forbidden_matches_nothing_in_fixture():
    fixture = load_fixture(FIXTURE_PATH)
    names = fixture["employees"] + fixture["projects"]
    assert fixture["forbidden"] == ["Sukma*", "Joko", "Ekspansi Pasar Eropa 2026"]
    for entry in fixture["forbidden"]:
        if entry.endswith("*"):
            prefix = entry[:-1]
            assert not [name for name in names if name.startswith(prefix)]
        else:
            assert not [name for name in names if entry in name]
