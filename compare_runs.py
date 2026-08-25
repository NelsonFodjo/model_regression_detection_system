"""
Compares the two most recent eval runs in eval_results/. This is the actual
regression check: did accuracy drop, and which specific cases flipped —
using overall_pass (category AND judge both had to pass).

Usage: python compare_runs.py
"""

import yaml
from pathlib import Path

RESULTS_DIR = Path("eval_results")
WARNING_THRESHOLD = 3.0   # percentage points
CRITICAL_THRESHOLD = 8.0  # percentage points


def load_latest_two_runs():
    files = sorted(RESULTS_DIR.glob("*.yaml"))
    if len(files) < 2:
        raise SystemExit(f"Need at least 2 runs in {RESULTS_DIR}/ to compare, found {len(files)}. Run run_eval.py again.")

    with open(files[-2]) as f:
        previous = yaml.safe_load(f)
    with open(files[-1]) as f:
        current = yaml.safe_load(f)

    return previous, current


def flag(delta):
    if delta <= -CRITICAL_THRESHOLD:
        return "CRITICAL REGRESSION"
    if delta <= -WARNING_THRESHOLD:
        return "WARNING: regression"
    if delta >= WARNING_THRESHOLD:
        return "improvement"
    return "no significant change"


def main():
    previous, current = load_latest_two_runs()

    print(f"Comparing {previous['prompt_version']} ({previous['started_at']}) -> {current['prompt_version']} ({current['started_at']})\n")

    for metric, label in [
        ("overall_pass_rate", "overall_pass_rate"),
        ("category_accuracy", "category_accuracy"),
        ("judge_accuracy", "judge_accuracy"),
        ("fact_coverage", "fact_coverage"),
    ]:
        prev_val = previous["summary"][metric]
        curr_val = current["summary"][metric]
        delta = curr_val - prev_val
        print(f"{label:20s} {prev_val:5.1f}% -> {curr_val:5.1f}%  ({delta:+.1f} pts)  [{flag(delta)}]")

    prev_tokens = previous["summary"].get("avg_tokens_per_case", 0)
    curr_tokens = current["summary"].get("avg_tokens_per_case", 0)
    token_delta = curr_tokens - prev_tokens
    print(f"{'avg_tokens_per_case':20s} {prev_tokens:5d}   -> {curr_tokens:5d}    ({token_delta:+d} tokens)")

    prev_by_id = {c["id"]: c for c in previous["cases"]}
    curr_by_id = {c["id"]: c for c in current["cases"]}

    regressions = []
    improvements = []

    for case_id, curr_case in curr_by_id.items():
        prev_case = prev_by_id.get(case_id)
        if not prev_case:
            continue

        prev_pass = prev_case.get("overall_pass", False)
        curr_pass = curr_case.get("overall_pass", False)

        if prev_pass and not curr_pass:
            regressions.append(case_id)
        elif not prev_pass and curr_pass:
            improvements.append(case_id)

    print()
    if regressions:
        print(f"Regressions (pass -> fail): {', '.join(regressions)}")
    else:
        print("No cases regressed.")

    if improvements:
        print(f"Improvements (fail -> pass): {', '.join(improvements)}")


if __name__ == "__main__":
    main()
