"""
The feature under test. One function: load a prompt version, classify one
email, return {"category": ..., "summary": ...}.
"""

import json
import yaml
from groq import Groq

MODEL = "openai/gpt-oss-20b"


def load_prompt(path):
    with open(path) as f:
        return yaml.safe_load(f)


def classify_email(client: Groq, prompt_config: dict, sender: str, subject: str, body: str) -> dict:
    messages = [
        {"role": "system", "content": prompt_config["system_prompt"]},
        {"role": "user", "content": f"From: {sender}\nSubject: {subject}\nBody:\n{body[:3000]}"},
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0,
        max_tokens=150,
        reasoning_effort="low",
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content.strip())
