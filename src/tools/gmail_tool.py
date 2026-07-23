"""Gmail read/send, exposed as agent tools."""
import base64
from email.mime.text import MIMEText
from src.tools.google_auth import get_gmail_service


def list_recent_emails(query: str = "is:unread", max_results: int = 10) -> list[dict]:
    service = get_gmail_service()
    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = result.get("messages", [])
    out = []
    for m in messages:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
        out.append({
            "id": m["id"],
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
        })
    return out


def send_email(to: str, subject: str, body: str) -> dict:
    service = get_gmail_service()
    message = MIMEText(body)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {"id": sent["id"], "status": "sent", "to": to}


TOOL_SCHEMAS = [
    {
        "name": "list_recent_emails",
        "description": "List recent emails matching a Gmail search query (default: unread).",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer"},
            },
        },
    },
    {
        "name": "send_email",
        "description": "Send an email on the user's behalf. Only call this when the user has clearly asked an email to be sent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    },
]

DISPATCH = {
    "list_recent_emails": list_recent_emails,
    "send_email": send_email,
}
