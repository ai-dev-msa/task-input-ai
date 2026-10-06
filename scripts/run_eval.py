"""FR-13 regression runner: replay eval/cases.jsonl through run() and score it.

Run (needs OPENAI_API_KEY in .env):
  .venv\\Scripts\\python.exe scripts\\run_eval.py
  .venv\\Scripts\\python.exe scripts\\run_eval.py --only timefmt-002
  .venv\\Scripts\\python.exe scripts\\run_eval.py --split dev --category ask --limit 5
  .venv\\Scripts\\python.exe scripts\\run_eval.py --update-baseline

Prints the report (headline metrics + delta against eval/baseline.json,
per-category table, confusion matrix, failures), writes eval/results.json,
and with --update-baseline copies it to eval/baseline.json.

Report-only: exit 0 whatever the scores; non-zero only for operational
errors (missing API key, unreadable cases/fixture).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from alokasi_agent import run
from alokasi_agent.eval import (
    aggregate,
    load_cases,
    load_fixture,
    score_turn,
)

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "eval" / "cases.jsonl"
FIXTURES_DIR = ROOT / "eval" / "fixtures"
RESULTS_PATH = ROOT / "eval" / "results.json"
BASELINE_PATH = ROOT / "eval" / "baseline.json"

# (label, key) pairs shown in the headline and compared against the baseline.
HEADLINE = (
    ("decision accuracy", "decision_accuracy"),
    ("row exact match", "row_exact_rate"),
    ("field accuracy", "field_accuracy"),
    ("clarification precision", "ask_precision"),
    ("clarification recall", "ask_recall"),
    ("optional field recall", "optional_field_recall"),
)
# The poem in this reply cannot be caught by substring checks — read it.
MANUAL_CHECK_ID = "oos-005"


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def flatten(text: Any, limit: int = 200) -> str:
    """One printable line out of a possibly multi-line reply."""
    line = " / ".join(str(text or "").splitlines())
    return line if len(line) <= limit else line[: limit - 3] + "..."


def summarize_case(scores: list[dict[str, Any]], api_errors: int) -> dict[str, Any]:
    """Per-case counts plus the blended score used for baseline deltas."""
    decision_correct = sum(int(s["decision_correct"]) for s in scores)
    row_exact = sum(1 for s in scores if s["row_exact"])
    row_total = sum(s["row_total"] for s in scores)
    field_correct = sum(s["field_correct"] for s in scores)
    field_total = sum(s["field_total"] for s in scores)
    checks = len(scores) + row_total + field_total
    return {
        "decision_correct": decision_correct,
        "decision_total": len(scores),
        "row_exact": row_exact,
        "row_total": row_total,
        "field_correct": field_correct,
        "field_total": field_total,
        "api_errors": api_errors,
        "score": round(
            (decision_correct + row_exact + field_correct) / max(1, checks), 4
        ),
    }


def print_report(
    metrics: dict[str, Any],
    case_results: dict[str, dict[str, Any]],
    failures: list[dict[str, Any]],
    manual_replies: list[tuple[int, Any]],
    case_count: int,
    turn_count: int,
) -> None:
    print(
        f"=== FR-13 eval: {case_count} cases, {turn_count} turns scored, "
        f"{metrics['api_error_count']} API errors ==="
    )

    baseline: dict[str, Any] | None = None
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    print("\nHeadline")
    for label, key in HEADLINE:
        line = f"  {label:<23}: {fmt(metrics[key])}"
        if baseline:
            old = baseline.get("metrics", {}).get(key)
            if old is not None and metrics[key] is not None:
                line += f" (baseline {fmt(old)}, delta {metrics[key] - old:+.3f})"
        print(line)
    print(f"  {'api errors':<23}: {metrics['api_error_count']}")

    if baseline:
        old_cases = baseline.get("cases", {})
        shared = [cid for cid in case_results if cid in old_cases]
        regressed, improved = [], []
        for cid in shared:
            delta = case_results[cid]["score"] - old_cases[cid]["score"]
            if delta < -1e-9:
                regressed.append(cid)
            elif delta > 1e-9:
                improved.append(cid)
        print("\nvs baseline (per case)")
        print(f"  regressed: {', '.join(regressed) or 'none'}")
        print(f"  improved : {', '.join(improved) or 'none'}")
    else:
        print("\nvs baseline: no eval/baseline.json yet (use --update-baseline)")

    print("\nPer category")
    print(f"  {'category':<18}{'decision':>10}{'rows':>10}{'fields':>10}")
    for category, group in sorted(metrics["per_category"].items()):
        decision = f"{group['decision_correct']}/{group['decision_total']}"
        rows = f"{group['row_exact']}/{group['row_total']}"
        fields = f"{group['field_correct']}/{group['field_total']}"
        print(f"  {category:<18}{decision:>10}{rows:>10}{fields:>10}")

    print("\nDecision confusion matrix (rows = expected, cols = predicted)")
    widths = {"call": 7, "confirm": 9, "ask": 7, "other": 8}
    print(f"  {'':<10}{'call':>7}{'confirm':>9}{'ask':>7}{'other':>8}")
    for expected, row in metrics["confusion"].items():
        cells = "".join(f"{row[p]:>{widths[p]}}" for p in widths)
        print(f"  {expected:<10}{cells}")

    print(f"\nFailures ({len(failures)})")
    for failure in failures:
        print(
            f"  {failure['id']} turn {failure['turn']}: expected "
            f"{failure['expected']}, got {failure['predicted']}"
        )
        print(f"      reply: {flatten(failure['reply'])}")

    if manual_replies:
        print("\nManual check")
        for turn, reply in manual_replies:
            print(f"  {MANUAL_CHECK_ID} turn {turn} (manual check): {flatten(reply)}")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="FR-13 eval runner (report-only)")
    parser.add_argument("--split", choices=["dev", "test"], help="keep one split")
    parser.add_argument("--category", help="keep one category tag")
    parser.add_argument("--only", help="comma-separated case ids")
    parser.add_argument("--limit", type=int, help="keep at most N cases")
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="copy this run's results to eval/baseline.json",
    )
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("error: OPENAI_API_KEY is not set (.env)", file=sys.stderr)
        return 2

    # Fail before spending any API calls if the data is unreadable.
    try:
        cases = load_cases(CASES_PATH)
        if args.split:
            cases = [c for c in cases if c["split"] == args.split]
        if args.category:
            cases = [c for c in cases if c["category"] == args.category]
        if args.only:
            wanted = {value.strip() for value in args.only.split(",") if value.strip()}
            cases = [c for c in cases if c["id"] in wanted]
        if args.limit is not None:
            cases = cases[: args.limit]
        prepared = [
            (
                case,
                datetime.fromisoformat(case["now"]),
                load_fixture(FIXTURES_DIR / f"{case['fixture']}.json"),
            )
            for case in cases
        ]
    except (OSError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    all_scores: list[dict[str, Any]] = []
    case_results: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    manual_replies: list[tuple[int, Any]] = []
    api_errors = 0

    for number, (case, now, fixture) in enumerate(prepared, start=1):
        print(f"[{number}/{len(prepared)}] {case['id']}")
        history: list[dict[str, Any]] | None = None
        scores: list[dict[str, Any]] = []
        case_errors = 0
        for turn_number, turn in enumerate(case["turns"], start=1):
            try:
                envelope, history = run(
                    turn["user"],
                    user_name=case["user_name"],
                    employees=fixture["employees"],
                    projects=fixture["projects"],
                    history=history,
                    now=now,
                )
            except Exception as error:  # API hiccup: count it, drop this case
                api_errors += 1
                case_errors += 1
                print(f"  API error on turn {turn_number}: {error}")
                break
            score = score_turn(turn["expect"], envelope)
            score["category"] = case["category"]
            scores.append(score)
            all_scores.append(score)
            if not score["decision_correct"] or (
                score["row_total"] and not score["row_exact"]
            ):
                failures.append(
                    {
                        "id": case["id"],
                        "turn": turn_number,
                        "expected": score["expected"],
                        "predicted": score["predicted"],
                        "reply": envelope.get("reply"),
                    }
                )
            if case["id"] == MANUAL_CHECK_ID:
                manual_replies.append((turn_number, envelope.get("reply")))
        case_results[case["id"]] = summarize_case(scores, case_errors)

    metrics = aggregate(all_scores, api_errors)
    print()
    print_report(
        metrics, case_results, failures, manual_replies, len(prepared), len(all_scores)
    )

    payload = {"metrics": metrics, "cases": case_results}
    RESULTS_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"\nwrote {RESULTS_PATH.relative_to(ROOT).as_posix()}")
    if args.update_baseline:
        BASELINE_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"updated {BASELINE_PATH.relative_to(ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
