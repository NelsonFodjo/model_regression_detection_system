"""
Run the classifier against golden_dataset.yaml and report:
1. Category accuracy — exact match against expected_category.
2. Fact coverage — do expected_facts (keywords) appear in the summary.
3. Judge accuracy — LLM-as-judge verdict on whether the summary is accurate.
4. Overall pass — a case only counts as PASS if category matches, the judge
   verdict is "pass", AND all expected_facts are present in the summary
   (100% fact coverage for that case).

Results are saved as YAML to eval_results/, mirroring what's printed here.

Usage: python run_eval.py [prompt_version]
Example: python run_eval.py v2
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from groq import Groq

from classifier import load_prompt, classify_email, judge_summary

RESULTS_DIR = Path("eval_results")


def facts_covered(summary: str, expected_facts: list[str]) -> tuple[list[str], list[str]]:
    """Returns (hit_facts, missing_facts) instead of just counts."""
    if not expected_facts:
        return [], []
    summary_lower = summary.lower()
    hit = [fact for fact in expected_facts if fact.lower() in summary_lower]
    missing = [fact for fact in expected_facts if fact.lower() not in summary_lower]
    return hit, missing


def _call_with_retry(func, *args, retries=2, **kwargs):
    """Retries once on transient API failures (empty/malformed generations)
    before giving up and letting the exception propagate."""
    last_error = None
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(1)
    raise last_error


def main():
    load_dotenv()

    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        raise SystemExit("Set GROQ_API_KEY as an environment variable before running.")

    prompt_version = sys.argv[1] if len(sys.argv) > 1 else "v1"
    prompt_path = f"prompts/{prompt_version}.yaml"

    client = Groq(api_key=groq_api_key)
    prompt_config = load_prompt(prompt_path)

    with open("golden_dataset.yaml") as f:
        cases = yaml.safe_load(f)

    run_started_at = datetime.now().astimezone()  # local time, correct UTC offset included
    print(f"Running {len(cases)} cases against prompt {prompt_version}")
    print(f"Started: {run_started_at.strftime('%Y-%m-%d %H:%M:%S %Z (UTC%z)')}\n")

    overall_passed = 0
    category_passed = 0
    judge_passed = 0
    total_facts_hit = 0
    total_facts_expected = 0
    total_tokens = 0
    case_records = []

    for case in cases:
        try:
            start = time.perf_counter()
            try:
                result = _call_with_retry(
                    classify_email, client, prompt_config, case["sender"], case["subject"], case["body"]
                )
            except Exception as e:
                raise RuntimeError(f"classify_email failed: {e}") from e
            latency = round(time.perf_counter() - start, 2)

            actual_category = result.get("category")
            actual_summary = result.get("summary", "")
            expected_category = case["expected_category"]

            category_ok = actual_category == expected_category
            if category_ok:
                category_passed += 1

            hit_facts, missing_facts = facts_covered(actual_summary, case.get("expected_facts", []))
            expected_count = len(case.get("expected_facts", []))
            hits = len(hit_facts)
            total_facts_hit += hits
            total_facts_expected += expected_count

            try:
                judge_result = _call_with_retry(
                    judge_summary, client, case["sender"], case["subject"], case["body"], actual_summary
                )
            except Exception as e:
                raise RuntimeError(f"judge_summary failed: {e}") from e
            judge_ok = judge_result.get("verdict") == "pass"
            judge_reason = judge_result.get("reason", "")
            if judge_ok:
                judge_passed += 1

            facts_ok = hits == expected_count

            overall_ok = category_ok and judge_ok and facts_ok
            if overall_ok:
                overall_passed += 1

            case_tokens = result.get("_usage", {}).get("total_tokens", 0) + judge_result.get("_usage", {}).get("total_tokens", 0)
            total_tokens += case_tokens

            case_records.append({
                "id": case["id"],
                "difficulty": case.get("difficulty"),
                "expected_category": expected_category,
                "actual_category": actual_category,
                "category_pass": category_ok,
                "judge_pass": judge_ok,
                "judge_reason": judge_reason,
                "facts_hit": hit_facts,
                "facts_missing": missing_facts,
                "facts_pass": facts_ok,
                "actual_summary": actual_summary,
                "latency_sec": latency,
                "tokens_used": case_tokens,
                "overall_pass": overall_ok,
            })

            status = "PASS" if overall_ok else "FAIL"
            judge_flag = "" if judge_ok else f" [judge:fail — {judge_reason}]"
            cat_flag = "" if category_ok else " [category:fail]"
            facts_flag = f" facts_hit={hit_facts} facts_missing={missing_facts}" if expected_count else ""
            print(f"{status}  {case['id']:10s} expected={expected_category:12s} got={actual_category}{cat_flag}{judge_flag}")
            if expected_count:
                print(f"          {facts_flag.strip()}")
            print(f"          summary: \"{actual_summary}\"")

        except Exception as e:
            print(f"ERROR {case['id']:10s} (after retries) {e}")
            case_records.append({
                "id": case["id"],
                "difficulty": case.get("difficulty"),
                "expected_category": case["expected_category"],
                "error": str(e),
                "overall_pass": False,
            })

    total = len(cases)
    category_accuracy = round(category_passed / total * 100, 1)
    judge_accuracy = round(judge_passed / total * 100, 1)
    overall_pass_rate = round(overall_passed / total * 100, 1)
    fact_coverage = round(total_facts_hit / total_facts_expected * 100, 1) if total_facts_expected else 0.0

    run_finished_at = datetime.now().astimezone()
    duration_sec = round((run_finished_at - run_started_at).total_seconds(), 1)

    print(f"\nOverall pass rate: {overall_passed}/{total} ({overall_pass_rate}%)  <- requires category + judge + 100% fact coverage, all three")
    print(f"Category accuracy: {category_passed}/{total} ({category_accuracy}%)")
    print(f"Judge accuracy:    {judge_passed}/{total} ({judge_accuracy}%)")
    print(f"Fact coverage:     {total_facts_hit}/{total_facts_expected} ({fact_coverage}%)")
    print(f"Total tokens used: {total_tokens} ({round(total_tokens / total)} avg/case)")
    print(f"Duration: {duration_sec}s")

    failed_ids = [c["id"] for c in case_records if not c["overall_pass"]]
    if failed_ids:
        print(f"\nFailed overall: {', '.join(failed_ids)}")

    # Save the full run as YAML, mirroring what was just printed
    RESULTS_DIR.mkdir(exist_ok=True)
    run_record = {
        "prompt_version": prompt_version,
        "started_at": run_started_at.isoformat(),
        "finished_at": run_finished_at.isoformat(),
        "duration_sec": duration_sec,
        "total_cases": total,
        "summary": {
            "overall_pass_rate": overall_pass_rate,
            "overall_passed": overall_passed,
            "category_accuracy": category_accuracy,
            "category_passed": category_passed,
            "judge_accuracy": judge_accuracy,
            "judge_passed": judge_passed,
            "fact_coverage": fact_coverage,
            "facts_hit": total_facts_hit,
            "facts_expected": total_facts_expected,
            "total_tokens": total_tokens,
            "avg_tokens_per_case": round(total_tokens / total),
        },
        "failed_case_ids": failed_ids,
        "cases": case_records,
    }

    out_path = RESULTS_DIR / f"{run_started_at.strftime('%Y%m%dT%H%M%S')}_{prompt_version}.yaml"
    with open(out_path, "w") as f:
        yaml.safe_dump(run_record, f, sort_keys=False, allow_unicode=True)
    print(f"\nSaved run to {out_path}")


if __name__ == "__main__":
    main()
