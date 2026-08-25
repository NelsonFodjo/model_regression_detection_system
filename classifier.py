"""
The feature under test (classify_email) and its judge (judge_summary).
Kept in one file — judge_summary is a separate function/prompt, but there's
no real reason to split it into its own module.
"""

import json
import yaml
from groq import Groq

MODEL = "openai/gpt-oss-20b"

JUDGE_PROMPT = """You are grading an email summary for accuracy.

Original email:
From: {sender}
Subject: {subject}
Body: {body}

Generated summary: "{summary}"

Does this summary accurately and specifically represent what the email is
about? It should mention the concrete subject matter, not just be vague or
generic. It should not contain facts that aren't in the email.

Respond with ONLY valid JSON: {{"verdict": "pass" or "fail", "reason": "<one short sentence>"}}"""


def load_prompt(path):
    with open(path) as f:
        return yaml.safe_load(f)


def classify_email(client: Groq, prompt_config: dict, sender: str, subject: str, body: str) -> dict:
    """The feature under test. Classifies one email into category + summary."""
    messages = [
        {"role": "system", "content": prompt_config["system_prompt"]},
        {"role": "user", "content": f"From: {sender}\nSubject: {subject}\nBody:\n{body[:3000]}"},
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
        max_tokens=500,
        reasoning_effort="low",
        response_format={"type": "json_object"},
    )

    parsed = json.loads(response.choices[0].message.content.strip())
    parsed["_usage"] = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }
    return parsed


def judge_summary(client: Groq, sender: str, subject: str, body: str, summary: str) -> dict:
    """Separate LLM call that grades whether a generated summary is accurate."""
    prompt = JUDGE_PROMPT.format(sender=sender, subject=subject, body=body[:1500], summary=summary)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=400,
        reasoning_effort="low",
        response_format={"type": "json_object"},
    )

    parsed = json.loads(response.choices[0].message.content.strip())
    parsed["_usage"] = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }
    return parsed