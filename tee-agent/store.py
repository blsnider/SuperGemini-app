"""Firestore state layer: bookings, preferences, audit log, heartbeats.

Collections:
  tee_agent_config/preferences      single doc, editable without redeploy
  tee_agent_bookings/<id>           one doc per reservation (active + history)
  tee_agent_audit/<auto-id>         every ForeUp call and decision
  tee_agent_heartbeats/watchdog     last successful watchdog run (§4.4)
  tee_agent_violations/<auto-id>    2-strike tracker (§ Phase 4)
"""

import logging
from datetime import datetime, timezone

from google.cloud import firestore

import config

logger = logging.getLogger(__name__)

# Booking statuses
ACTIVE = "active"                  # booked, watchdog is managing it
CANCEL_PENDING = "cancel_pending"  # check tripped, waiting on Byron (§4.3)
CANCELED = "canceled"
CANCEL_FAILED = "cancel_failed"    # API cancel failed after retries — §4.4 fired
PLAYED = "played"
DRY_RUN = "dry_run"                # what we *would* have booked

_db = None


def db() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(project=config.GCP_PROJECT)
    return _db


def get_preferences() -> dict:
    """Load preferences, creating the doc with defaults on first run."""
    ref = db().collection("tee_agent_config").document("preferences")
    snap = ref.get()
    if not snap.exists:
        ref.set(config.DEFAULT_PREFERENCES)
        logger.info("Created default preferences doc in Firestore")
        return dict(config.DEFAULT_PREFERENCES)
    prefs = dict(config.DEFAULT_PREFERENCES)
    prefs.update(snap.to_dict())
    return prefs


def save_booking(booking: dict) -> str:
    booking.setdefault("created_at", datetime.now(timezone.utc))
    booking.setdefault("status", ACTIVE)
    ref = db().collection("tee_agent_bookings").document(str(booking["reservation_id"]))
    ref.set(booking)
    return ref.id


def update_booking(reservation_id: str, fields: dict) -> None:
    fields["updated_at"] = datetime.now(timezone.utc)
    db().collection("tee_agent_bookings").document(str(reservation_id)).update(fields)


def get_booking(reservation_id: str) -> dict | None:
    snap = db().collection("tee_agent_bookings").document(str(reservation_id)).get()
    return snap.to_dict() if snap.exists else None


def active_bookings() -> list[dict]:
    query = db().collection("tee_agent_bookings").where(
        filter=firestore.FieldFilter("status", "in", [ACTIVE, CANCEL_PENDING])
    )
    return [s.to_dict() | {"reservation_id": s.id} for s in query.stream()]


def bookings_for_week(week_key: str) -> int:
    """Count non-canceled bookings tagged with the given ISO week (hoarding cap §3.2)."""
    query = db().collection("tee_agent_bookings").where(
        filter=firestore.FieldFilter("week_key", "==", week_key)
    )
    return sum(1 for s in query.stream() if s.to_dict().get("status") != CANCELED)


def audit(event: str, detail: dict | None = None) -> None:
    try:
        db().collection("tee_agent_audit").add({
            "event": event,
            "detail": detail or {},
            "at": datetime.now(timezone.utc),
        })
    except Exception as e:  # auditing must never break the main flow
        logger.error("Audit write failed for %s: %s", event, e)


def heartbeat(name: str = "watchdog") -> None:
    """Written at the END of each successful run; a separate monitor alerts on
    staleness (§4.4 — a silent dead watchdog is how violations happen)."""
    db().collection("tee_agent_heartbeats").document(name).set(
        {"last_run": datetime.now(timezone.utc)}
    )


def record_violation(reason: str, booking: dict) -> int:
    """Track Fargo's 2-strike policy; returns season total."""
    col = db().collection("tee_agent_violations")
    col.add({"reason": reason, "booking": booking, "at": datetime.now(timezone.utc)})
    year = str(datetime.now(timezone.utc).year)
    return sum(1 for s in col.stream() if s.to_dict()["at"].strftime("%Y") == year)
