"""Google Calendar conflict check (§4.2), read-only on Byron's calendar.

Uses the Cloud Run service account via Application Default Credentials.
TODO Byron (§7): share your personal calendar (read-only / free-busy) with the
tee-agent service account email, and set CALENDAR_ID below or in env.
"""

import logging
import os
from datetime import datetime, timedelta

import google.auth
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

CALENDAR_ID = os.getenv("TEE_AGENT_CALENDAR_ID", "primary")
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
# Events created by the sniper carry this marker so they don't conflict with themselves.
TEE_EVENT_MARKER = "booked by tee-agent"


def _service():
    creds, _ = google.auth.default(scopes=SCOPES)
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def conflicts(tee_time: datetime, travel_buffer_minutes: int, round_duration_hours: float) -> list[str]:
    """Return summaries of non-tee-time events overlapping
    [tee − travel buffer, tee + round duration] (§4.2). Empty list = clear."""
    window_start = tee_time - timedelta(minutes=travel_buffer_minutes)
    window_end = tee_time + timedelta(hours=round_duration_hours)
    result = _service().events().list(
        calendarId=CALENDAR_ID,
        timeMin=window_start.isoformat(),
        timeMax=window_end.isoformat(),
        singleEvents=True,
        orderBy="startTime",
    ).execute()
    return [
        ev.get("summary", "(untitled event)")
        for ev in result.get("items", [])
        if TEE_EVENT_MARKER not in ev.get("summary", "").lower()
        and ev.get("transparency") != "transparent"  # ignore free/available events
    ]


def create_tee_event(course: str, tee_time: datetime, round_duration_hours: float) -> str | None:
    """Create the '⛳ ... — booked by tee-agent' event (§3.2). Returns event id."""
    try:
        ev = _service().events().insert(calendarId=CALENDAR_ID, body={
            "summary": f"⛳ {course} {tee_time.strftime('%-I:%M %p')} — {TEE_EVENT_MARKER}",
            "start": {"dateTime": tee_time.isoformat()},
            "end": {"dateTime": (tee_time + timedelta(hours=round_duration_hours)).isoformat()},
        }).execute()
        return ev.get("id")
    except Exception as e:
        # Calendar write needs writer access; booking still stands without it.
        logger.warning("Could not create calendar event: %s", e)
        return None


def delete_tee_event(event_id: str) -> None:
    try:
        _service().events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
    except Exception as e:
        logger.warning("Could not delete calendar event %s: %s", event_id, e)
