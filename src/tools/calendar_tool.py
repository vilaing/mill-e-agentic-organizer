"""Google Calendar read/write, exposed as agent tools."""
import datetime
from src.tools.google_auth import get_calendar_service


def list_upcoming_events(days_ahead: int = 7) -> list[dict]:
    service = get_calendar_service()
    now = datetime.datetime.utcnow().isoformat() + "Z"
    later = (datetime.datetime.utcnow() + datetime.timedelta(days=days_ahead)).isoformat() + "Z"
    result = service.events().list(
        calendarId="primary", timeMin=now, timeMax=later,
        singleEvents=True, orderBy="startTime",
    ).execute()
    events = result.get("items", [])
    return [
        {
            "id": e["id"],
            "summary": e.get("summary", "(no title)"),
            "start": e["start"].get("dateTime", e["start"].get("date")),
        }
        for e in events
    ]


def create_event(summary: str, start_iso: str, end_iso: str, description: str = "") -> dict:
    service = get_calendar_service()
    event = {
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
    }
    created = service.events().insert(calendarId="primary", body=event).execute()
    return {"id": created["id"], "summary": summary, "status": "created"}


TOOL_SCHEMAS = [
    {
        "name": "list_upcoming_events",
        "description": "List calendar events in the next N days.",
        "input_schema": {
            "type": "object",
            "properties": {"days_ahead": {"type": "integer"}},
        },
    },
    {
        "name": "create_event",
        "description": "Create a calendar event. start_iso/end_iso must be ISO 8601 datetimes, e.g. 2026-08-01T14:00:00-07:00.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "start_iso": {"type": "string"},
                "end_iso": {"type": "string"},
                "description": {"type": "string"},
            },
            "required": ["summary", "start_iso", "end_iso"],
        },
    },
]

DISPATCH = {
    "list_upcoming_events": list_upcoming_events,
    "create_event": create_event,
}
