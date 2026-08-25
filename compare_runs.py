"""
Compares the two most recent eval runs in eval_results/. This is the actual
regression check: did accuracy drop, and which specific cases flipped —
using overall_pass (category AND judge both had to pass).

Usage: python compare_runs.py [current_version] [previous_version]
Example: python compare_runs.py v2 v1
"""

import os
import sys
import yaml
import requests
from pathlib import Path
from dotenv import load_dotenv

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

def load_version_run(version: str):
    files = sorted(RESULTS_DIR.glob(f"*_{version}.yaml"))
    if not files:
        raise SystemExit(f"No evaluation run found for prompt version {version!r} in {RESULTS_DIR}/.")

    with open(files[-1]) as f:
        return yaml.safe_load(f)


def load_runs():
    if len(sys.argv) == 1:
        return load_latest_two_runs()
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python compare_runs.py [current_version] [previous_version]")

    current_version, previous_version = sys.argv[1:]
    return load_version_run(previous_version), load_version_run(current_version)


def flag(delta):
    if delta <= -CRITICAL_THRESHOLD:
        return "CRITICAL REGRESSION"
    if delta <= -WARNING_THRESHOLD:
        return "WARNING: regression"
    if delta >= WARNING_THRESHOLD:
        return "improvement"
    return "no significant change"


def send_slack_alert(message: str):
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("\n(No SLACK_WEBHOOK_URL set — skipping Slack alert.)")
        return

    response = requests.post(webhook_url, json={"text": message})
    if response.status_code == 200:
        print("\nSlack alert sent.")
    else:
        print(f"\nSlack alert failed ({response.status_code}): {response.text}")


def main():
    load_dotenv()
    previous, current = load_runs()

    print(f"Comparing {previous['prompt_version']} ({previous['started_at']}) -> {current['prompt_version']} ({current['started_at']})\n")

    metric_lines = []
    regression_detected = False
    critical_detected = False

    for metric, label in [
        ("overall_pass_rate", "overall_pass_rate"),
        ("category_accuracy", "category_accuracy"),
        ("judge_accuracy", "judge_accuracy"),
        ("fact_coverage", "fact_coverage"),
    ]:
        prev_val = previous["summary"][metric]
        curr_val = current["summary"][metric]
        delta = curr_val - prev_val
        status = flag(delta)
        line = f"{label:20s} {prev_val:5.1f}% -> {curr_val:5.1f}%  ({delta:+.1f} pts)  [{status}]"
        print(line)
        metric_lines.append(line)

        if "REGRESSION" in status:
            critical_detected = True
            regression_detected = True
        elif "WARNING" in status:
            regression_detected = True

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
        regression_detected = True
    else:
        print("No cases regressed.")

    if improvements:
        print(f"Improvements (fail -> pass): {', '.join(improvements)}")

    if regression_detected:
        severity = "CRITICAL" if critical_detected else "WARNING"
        alert_lines = [
            f"*[{severity}] Regression detected: {previous['prompt_version']} -> {current['prompt_version']}*",
            "",
            *[f"`{l}`" for l in metric_lines],
        ]
        if regressions:
            alert_lines.append(f"\nCases that flipped pass -> fail: {', '.join(regressions)}")

        send_slack_alert("\n".join(alert_lines))
    else:
        print("\nNo regression — Slack alert not sent.")


if __name__ == "__main__":
    main()
