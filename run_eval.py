"""
Run the classifier against golden_dataset.yaml and report three scores:
1. Category accuracy — exact match against expected_category.
2. Fact coverage — do expected_facts (keywords) appear in the summary.
3. Judge accuracy — LLM-as-judge verdict on whether the summary is accurate.

Usage: python run_eval.py [prompt_version]
Example: python run_eval.py v2
"""

import os
import sys
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from groq import Groq

from classifier import load_prompt, classify_email, judge_summary

RESULTS_DIR = Path("eval_results")


def facts_covered(summary: str, expected_facts: list[str]) -> tuple[int, int]:
    if not expected_facts:
        return 0, 0
    summary_lower = summary.lower()
    hits = sum(1 for fact in expected_facts if fact.lower() in summary_lower)
    return hits, len(expected_facts)


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

    print(f"Running {len(cases)} cases against prompt {prompt_version}\n")

    category_passed = 0
    judge_passed = 0
    total_facts_hit = 0
    total_facts_expected = 0
    failed_category_cases = []
    failed_judge_cases = []
    per_case_results = {}

    for case in cases:
        try:
            start = time.time()
            result = classify_email(client, prompt_config, case["sender"], case["subject"], case["body"])
            latency = round(time.time() - start, 2)

            actual_category = result.get("category")
            actual_summary = result.get("summary", "")
            expected_category = case["expected_category"]

            category_ok = actual_category == expected_category
            if category_ok:
                category_passed += 1
            else:
                failed_category_cases.append(case["id"])

            hits, expected_count = facts_covered(actual_summary, case.get("expected_facts", []))
            total_facts_hit += hits
            total_facts_expected += expected_count

            judge_result = judge_summary(client, case["sender"], case["subject"], case["body"], actual_summary)
            judge_ok = judge_result.get("verdict") == "pass"
            if judge_ok:
                judge_passed += 1
            else:
                failed_judge_cases.append((case["id"], judge_result.get("reason", "")))

            per_case_results[case["id"]] = {
                "category_pass": category_ok,
                "judge_pass": judge_ok,
                "facts_hit": hits,
                "facts_expected": expected_count,
                "latency_sec": latency,
            }

            status = "PASS" if category_ok else "FAIL"
            judge_flag = "" if judge_ok else " [judge:fail]"
            facts_flag = f" facts={hits}/{expected_count}" if expected_count else ""
            print(f"{status}  {case['id']:10s} expected={expected_category:12s} got={actual_category}{facts_flag}{judge_flag}")

        except Exception as e:
            failed_category_cases.append(case["id"])
            per_case_results[case["id"]] = {"error": str(e)}
            print(f"ERROR {case['id']:10s} {e}")

    total = len(cases)
    category_accuracy = category_passed / total * 100
    judge_accuracy = judge_passed / total * 100
    fact_coverage = (total_facts_hit / total_facts_expected * 100) if total_facts_expected else 0

    print(f"\nCategory accuracy: {category_passed}/{total} ({category_accuracy:.1f}%)")
    print(f"Fact coverage:     {total_facts_hit}/{total_facts_expected} ({fact_coverage:.1f}%)")
    print(f"Judge accuracy:    {judge_passed}/{total} ({judge_accuracy:.1f}%)")

    if failed_category_cases:
        print(f"\nFailed category: {', '.join(failed_category_cases)}")
    if failed_judge_cases:
        print("Failed judge:")
        for case_id, reason in failed_judge_cases:
            print(f"  {case_id}: {reason}")

    # Save this run so compare_runs.py has something to diff against
    RESULTS_DIR.mkdir(exist_ok=True)
    run_record = {
        "prompt_version": prompt_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "category_accuracy": category_accuracy,
        "judge_accuracy": judge_accuracy,
        "fact_coverage": fact_coverage,
        "cases": per_case_results,
    }
    out_path = RESULTS_DIR / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{prompt_version}.json"
    with open(out_path, "w") as f:
        json.dump(run_record, f, indent=2)
    print(f"\nSaved run to {out_path}")


if __name__ == "__main__":
    main()
