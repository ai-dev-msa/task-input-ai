"""Pure scoring functions for the FR-12/FR-13 eval runner.

Everything here is offline and unit-testable: the only I/O is reading the
cases and fixture files. Live API calls live in scripts/run_eval.py.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# The four decision classes reported by classify() (cancel/refuse collapse
# into "other", drop_review into "confirm").
DECISION_CLASSES = ("call", "confirm", "ask", "other")

# expect.kind -> decision class; row-bearing kinds carry rows/calls gold.
EXPECTED_KIND = {
    "confirm": "confirm",
    "drop_review": "confirm",
    "call": "call",
    "ask": "ask",
    "cancel": "other",
    "refuse": "other",
}
ROW_KINDS = ("confirm", "drop_review", "call")
OPTIONAL_FIELDS = ("review", "tim_pekerjaan")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RANGE = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    """Read the JSONL case file; a bad line raises with its line number."""
    cases: list[dict[str, Any]] = []
    text = Path(path).read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            cases.append(json.loads(line))
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{number}: {error}") from error
    return cases


def load_fixture(path: str | Path) -> dict[str, Any]:
    """Read one fixture file ({employees, projects, forbidden})."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _clean_last_part(part: str) -> str:
    """Strip the trailing 'Benar?' / 'Salah?' / '.' the summary line ends with."""
    part = part.strip()
    for suffix in ("Benar?", "Salah?"):
        if part.endswith(suffix):
            part = part[: -len(suffix)].strip()
    return part.rstrip(".").strip()


def parse_summary(reply: str | None) -> list[dict[str, str]]:
    """Rows parsed from the confirmation summary in a reply.

    Each line is split on '|':
      nama | proyek | tanggal | jenis | jam_mulai-jam_selesai
      plus ' | review' and ' | tim_pekerjaan' when present.
    Lines with fewer than 5 parts are not summaries (the drop_review notice,
    chatter) and are ignored; a summary-shaped line that will not parse
    makes the whole reply unparseable (a confirm turn then scores 0 fields).
    """
    rows: list[dict[str, str]] = []
    for line in (reply or "").splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 5:
            continue
        if len(parts) > 7:
            return []
        parts[-1] = _clean_last_part(parts[-1])
        nama, proyek, tanggal, jenis, jam = parts[:5]
        if not (nama and proyek and tanggal and jenis and jam):
            return []
        if not _DATE.match(tanggal) or not _TIME_RANGE.match(jam):
            return []
        mulai, selesai = jam.split("-")
        row = {
            "nama_karyawan": nama,
            "nama_proyek": proyek,
            "tanggal": tanggal,
            "jenis_pekerjaan": jenis,
            "jam_mulai": mulai,
            "jam_selesai": selesai,
        }
        for key, value in zip(OPTIONAL_FIELDS, parts[5:]):
            if value:
                row[key] = value
        rows.append(row)
    return rows


def classify(envelope: dict[str, Any]) -> str:
    """Decision class of one reply: call | confirm | ask | other.

    Order is the rule: a tool call wins; otherwise a parseable summary is a
    confirmation; otherwise a '?' makes it a clarification — so an ask never
    carries a call and never emits a summary.
    """
    if envelope.get("type") == "function_call":
        return "call"
    reply = envelope.get("reply") or ""
    if parse_summary(reply):
        return "confirm"
    if "?" in reply:
        return "ask"
    return "other"


def _call_rows(envelope: dict[str, Any]) -> list[dict[str, Any]]:
    """Gold-shaped rows out of a function_call envelope (object or array)."""
    if envelope.get("type") != "function_call":
        return []
    try:
        arguments = json.loads(envelope.get("arguments") or "")
    except json.JSONDecodeError:
        return []
    return arguments if isinstance(arguments, list) else [arguments]


def score_turn(expect: dict[str, Any], envelope: dict[str, Any]) -> dict[str, Any]:
    """Scores for one turn. `category` is stamped on by the runner."""
    predicted = classify(envelope)
    expected = EXPECTED_KIND[expect["kind"]]
    score: dict[str, Any] = {
        "expected": expected,
        "predicted": predicted,
        "decision_correct": predicted == expected,
        "row_exact": None,
        "row_total": 0,
        "field_correct": 0,
        "field_total": 0,
        "optional_correct": 0,
        "optional_total": 0,
    }
    if expect["kind"] not in ROW_KINDS:
        return score

    exp_rows: list[dict[str, Any]] = expect.get("rows") or expect.get("calls") or []
    if predicted == "call":
        pred_rows = _call_rows(envelope)
    elif predicted == "confirm":
        pred_rows = parse_summary(envelope.get("reply"))
    else:
        pred_rows = []

    score["row_total"] = 1
    score["row_exact"] = pred_rows == exp_rows

    # Field accuracy: rows aligned by index; a field counts only when both
    # sides carry it and agree, so a phantom "review": "" is a miss.
    field_correct = 0
    field_total = 0
    for index, exp_row in enumerate(exp_rows):
        pred_row = pred_rows[index] if index < len(pred_rows) else {}
        keys = set(exp_row) | set(pred_row)
        field_total += len(keys)
        field_correct += sum(
            1
            for key in keys
            if key in exp_row and key in pred_row and exp_row[key] == pred_row[key]
        )
    for extra_row in pred_rows[len(exp_rows) :]:
        field_total += len(extra_row)
    score["field_correct"] = field_correct
    score["field_total"] = field_total

    # Optional-field recall: of the expected optional fields, how many the
    # reply actually carried (non-empty) on the aligned row.
    for index, exp_row in enumerate(exp_rows):
        for key in OPTIONAL_FIELDS:
            if key not in exp_row:
                continue
            score["optional_total"] += 1
            if index < len(pred_rows) and pred_rows[index].get(key):
                score["optional_correct"] += 1
    return score


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def aggregate(
    scores: list[dict[str, Any]], api_errors: int = 0
) -> dict[str, Any]:
    """Metric totals over scored turns (api-error turns are not in `scores`)."""
    metrics: dict[str, Any] = {
        "decision_correct": 0,
        "decision_total": 0,
        "decision_accuracy": None,
        "row_exact": 0,
        "row_total": 0,
        "row_exact_rate": None,
        "field_correct": 0,
        "field_total": 0,
        "field_accuracy": None,
        "ask_expected": 0,
        "ask_predicted": 0,
        "ask_correct": 0,
        "ask_precision": None,
        "ask_recall": None,
        "optional_correct": 0,
        "optional_total": 0,
        "optional_field_recall": None,
        "api_error_count": api_errors,
        "confusion": {
            expected: {predicted: 0 for predicted in DECISION_CLASSES}
            for expected in DECISION_CLASSES
        },
        "per_category": {},
    }
    for score in scores:
        expected = score["expected"]
        predicted = score["predicted"]
        metrics["decision_total"] += 1
        metrics["decision_correct"] += int(score["decision_correct"])
        metrics["confusion"][expected][predicted] += 1
        if expected == "ask":
            metrics["ask_expected"] += 1
        if predicted == "ask":
            metrics["ask_predicted"] += 1
        if expected == "ask" and predicted == "ask":
            metrics["ask_correct"] += 1
        metrics["row_total"] += score["row_total"]
        metrics["row_exact"] += int(bool(score["row_exact"]))
        metrics["field_correct"] += score["field_correct"]
        metrics["field_total"] += score["field_total"]
        metrics["optional_correct"] += score["optional_correct"]
        metrics["optional_total"] += score["optional_total"]

        category = score.get("category", "")
        group = metrics["per_category"].setdefault(
            category,
            {
                "decision_correct": 0,
                "decision_total": 0,
                "row_exact": 0,
                "row_total": 0,
                "field_correct": 0,
                "field_total": 0,
            },
        )
        group["decision_total"] += 1
        group["decision_correct"] += int(score["decision_correct"])
        group["row_total"] += score["row_total"]
        group["row_exact"] += int(bool(score["row_exact"]))
        group["field_correct"] += score["field_correct"]
        group["field_total"] += score["field_total"]

    metrics["decision_accuracy"] = _rate(
        metrics["decision_correct"], metrics["decision_total"]
    )
    metrics["row_exact_rate"] = _rate(metrics["row_exact"], metrics["row_total"])
    metrics["field_accuracy"] = _rate(
        metrics["field_correct"], metrics["field_total"]
    )
    metrics["ask_precision"] = _rate(
        metrics["ask_correct"], metrics["ask_predicted"]
    )
    metrics["ask_recall"] = _rate(metrics["ask_correct"], metrics["ask_expected"])
    metrics["optional_field_recall"] = _rate(
        metrics["optional_correct"], metrics["optional_total"]
    )
    return metrics
