"""
The feature under test (classify_email) and its judge (judge_summary).
Kept in one file — judge_summary is a separate function/prompt, but there's
no real reason to split it into its own module.
"""

import json
import os
import yaml
from openai import OpenAI

def get_model() -> str:
    model = os.environ.get("MODEL")
    if not model:
        raise RuntimeError("Set MODEL as an environment variable before making AI requests.")
    return model

JUDGE_PROMPT = """You are grading an email summary for accuracy.

Original email:
From: {sender}
Subject: {subject}
Body: {body}

Generated summary: "{summary}"

Does this summary accurately and sufficiently specifically represent the email?
Pass it when it captures the concrete subject matter and does not invent facts.
Do not fail merely because it omits secondary details that are not necessary to
identify the email's subject. Fail only when it is vague, materially incomplete,
or contains facts not present in the original email.

Respond with ONLY valid JSON: {{"verdict": "pass" or "fail", "reason": "<one short sentence>"}}"""


def load_prompt(path):
    with open(path) as f:
        return yaml.safe_load(f)


def _parse_json_response(response, required_fields: tuple[str, ...]) -> dict:
    content = response.choices[0].message.content
    if not content:
        raise ValueError("The model returned an empty response.")

    try:
        parsed = json.loads(content.strip())
    except json.JSONDecodeError as error:
        raise ValueError("The model returned invalid JSON.") from error

    if not isinstance(parsed, dict):
        raise ValueError("The model response must be a JSON object.")

    for field in required_fields:
        if not isinstance(parsed.get(field), str) or not parsed[field].strip():
            raise ValueError(f"The model response must include a non-empty {field}.")

    return parsed


def classify_email(client: OpenAI, prompt_config: dict, sender: str, subject: str, body: str) -> dict:
    """The feature under test. Classifies one email into category + summary."""
    messages = [
        {"role": "system", "content": prompt_config["system_prompt"]},
        {"role": "user", "content": f"From: {sender}\nSubject: {subject}\nBody:\n{body[:3000]}"},
    ]

    response = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=0,
        max_tokens=500,
        reasoning_effort="none",
        response_format={"type": "json_object"},
    )

    parsed = _parse_json_response(response, ("category", "summary"))
    parsed["_usage"] = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }
    return parsed


def judge_summary(client: OpenAI, sender: str, subject: str, body: str, summary: str) -> dict:
    """Separate LLM call that grades whether a generated summary is accurate."""
    prompt = JUDGE_PROMPT.format(sender=sender, subject=subject, body=body[:1500], summary=summary)

    response = client.chat.completions.create(
        model=get_model(),
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=400,
        reasoning_effort="none",
        response_format={"type": "json_object"},
    )

    parsed = _parse_json_response(response, ("verdict", "reason"))
    if parsed["verdict"].lower() not in {"pass", "fail"}:
        raise ValueError("The judge verdict must be either pass or fail.")
    parsed["_usage"] = {
        "prompt_tokens": response.usage.prompt_tokens,
        "completion_tokens": response.usage.completion_tokens,
        "total_tokens": response.usage.total_tokens,
    }
    return parsed
