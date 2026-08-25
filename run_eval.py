"""
Run the classifier against golden_dataset.yaml and report pass/fail per case
plus overall accuracy. This is the regression check: run it after any prompt
change and see if accuracy dropped.

Usage: python run_eval.py [prompt_version]
Example: python run_eval.py v1
"""

import os
import sys
import yaml
from dotenv import load_dotenv
from groq import Groq

from classifier import load_prompt, classify_email


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

    passed = 0
    failed_cases = []

    for case in cases:
        result = classify_email(client, prompt_config, case["sender"], case["subject"], case["body"])
        actual = result.get("category")
        expected = case["expected_category"]

        if actual == expected:
            passed += 1
            print(f"PASS  {case['id']:10s} expected={expected}")
        else:
            failed_cases.append(case["id"])
            print(f"FAIL  {case['id']:10s} expected={expected:12s} got={actual}  ({case['difficulty']})")

    total = len(cases)
    accuracy = passed / total * 100

    print(f"\n{passed}/{total} passed ({accuracy:.1f}%)")
    if failed_cases:
        print(f"Failed: {', '.join(failed_cases)}")


if __name__ == "__main__":
    main()
