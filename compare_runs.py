"""
Compares the two most recent eval runs in eval_results/. This is the actual
regression check: did accuracy drop, and which specific cases flipped.

Usage: python compare_runs.py
"""

import json
from pathlib import Path

RESULTS_DIR = Path("eval_results")
WARNING_THRESHOLD = 3.0   # percentage points
CRITICAL_THRESHOLD = 8.0  # percentage points


def load_latest_two_runs():
    files = sorted(RESULTS_DIR.glob("*.json"))
    if len(files) < 2:
        raise SystemExit(f"Need at least 2 runs in {RESULTS_DIR}/ to compare, found {len(files)}. Run run_eval.py again.")

    with open(files[-2]) as f:
        previous = json.load(f)
    with open(files[-1]) as f:
        current = json.load(f)

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

    print(f"Comparing {previous['prompt_version']} ({previous['timestamp']}) -> {current['prompt_version']} ({current['timestamp']})\n")

    for metric in ["category_accuracy", "judge_accuracy", "fact_coverage"]:
        prev_val = previous[metric]
        curr_val = current[metric]
        delta = curr_val - prev_val
        print(f"{metric:20s} {prev_val:5.1f}% -> {curr_val:5.1f}%  ({delta:+.1f} pts)  [{flag(delta)}]")

    # Per-case flips
    prev_cases = previous["cases"]
    curr_cases = current["cases"]

    regressions = []
    improvements = []

    for case_id in curr_cases:
        if case_id not in prev_cases:
            continue
        prev_pass = prev_cases[case_id]["category_pass"]
        curr_pass = curr_cases[case_id]["category_pass"]

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