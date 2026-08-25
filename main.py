"""
Mail Summary — reads unread Gmail messages and generates a title + summary
using Groq.

Run: python main.py
"""

import os
import json
import base64
from pathlib import Path

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from groq import Groq

# --- Config ---
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
PROCESSED_FILE = "processed_ids.json"
GROQ_MODEL = "openai/gpt-oss-20b"


def get_gmail_service():
    """Authenticate with Gmail API, caching the token after first login."""
    creds = None

    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def load_processed_ids():
    if Path(PROCESSED_FILE).exists():
        with open(PROCESSED_FILE) as f:
            return set(json.load(f))
    return set()


def save_processed_ids(ids):
    with open(PROCESSED_FILE, "w") as f:
        json.dump(list(ids), f)


def get_unread_messages(service, max_results=10):
    """Fetch the N most recent unread messages, regardless of category tab."""
    results = (
        service.users()
        .messages()
        .list(
            userId="me",
            q="is:unread category:primary",
            maxResults=max_results,
        )
        .execute()
    )
    return results.get("messages", [])

def extract_body(payload):
    """Pull plain text body out of a Gmail message payload."""
    if "parts" in payload:
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode(
                    "utf-8", errors="ignore"
                )
            # Recurse into nested multipart messages
            if "parts" in part:
                nested = extract_body(part)
                if nested:
                    return nested
    elif "body" in payload and "data" in payload["body"]:
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
            "utf-8", errors="ignore"
        )
    return ""


def get_message_details(service, msg_id):
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()

    headers = msg["payload"]["headers"]
    subject = next((h["value"] for h in headers if h["name"] == "Subject"), "(no subject)")
    sender = next((h["value"] for h in headers if h["name"] == "From"), "(unknown sender)")
    body = extract_body(msg["payload"])
    timestamp = int(msg.get("internalDate", 0))

    return {"id": msg_id, "subject": subject, "sender": sender, "body": body, "timestamp": timestamp}


def categorize(groq_client, subject, sender, body):
    """Ask Groq for a single-word category label for the email."""
    prompt = f"""Classify this email with exactly ONE word (a category label,
e.g. Work, Newsletter, Promotion, Finance, Social, Travel, Support, Personal,
Learning, News, Community, Productivity, Recruiting, Crypto, Faith, Meeting, Spam).

From: {sender}
Subject: {subject}
Body:
{body[:2000]}

Respond with only the single category word, nothing else."""

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=100,
        reasoning_effort="low",
    )
    return response.choices[0].message.content.strip()


def main():
    load_dotenv()

    groq_api_key = os.environ.get("GROQ_API_KEY")
    if not groq_api_key:
        raise SystemExit("Set GROQ_API_KEY as an environment variable before running.")

    groq_client = Groq(api_key=groq_api_key)
    service = get_gmail_service()

    processed_ids = load_processed_ids()
    messages = get_unread_messages(service)

    new_messages = [m for m in messages if m["id"] not in processed_ids]

    if not new_messages:
        print("No new unread mail.")
        return

    print(f"Found {len(new_messages)} new unread message(s).\n")

    details_list = [get_message_details(service, m["id"]) for m in new_messages]
    details_list.sort(key=lambda d: d["timestamp"], reverse=True)

    for details in details_list:
        category = categorize(groq_client, details["subject"], details["sender"], details["body"])

        print(f"[{category}] {details['subject']}  —  {details['sender']}")

        processed_ids.add(details["id"])

    save_processed_ids(processed_ids)


if __name__ == "__main__":
    main()