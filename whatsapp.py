"""Send formatted mail summaries through the WhatsApp Cloud API."""

import os

import requests


def _normalize_recipient(value: str) -> str:
    """Return an international WhatsApp number in digits-only format."""
    return "".join(character for character in value if character.isdigit())


def format_summary(details: dict, result: dict) -> str:
    """Build a compact WhatsApp message using WhatsApp markdown."""
    return (
        "*EMAIL SUMMARY*\n"
        f"*{result['category'].upper()}*\n\n"
        "*SUMMARY*\n"
        f"{result['summary']}\n\n"
        "*EMAIL DETAILS*\n"
        f"From: {details['sender']}\n"
        f"Subject: {details['subject']}"
    )


def send_whatsapp_message(message: str) -> None:
    """Send one text message through the WhatsApp Cloud API."""
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    recipient = os.environ.get("WHATSAPP_TO")

    missing = [
        name
        for name, value in {
            "WHATSAPP_PHONE_NUMBER_ID": phone_number_id,
            "WHATSAPP_ACCESS_TOKEN": access_token,
            "WHATSAPP_TO": recipient,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Set WhatsApp configuration in .env: {', '.join(missing)}")
    if recipient is None:
        raise RuntimeError("WHATSAPP_TO must contain an international phone number.")
    recipient = _normalize_recipient(recipient)
    if not recipient:
        raise RuntimeError("WHATSAPP_TO must contain an international phone number.")

    response = requests.post(
        f"https://graph.facebook.com/v23.0/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient,
            "type": "text",
            "text": {"preview_url": False, "body": message},
        },
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError(f"WhatsApp delivery failed ({response.status_code}): {response.text}")