"""Watchdog (§4): every 30 minutes, decide keep/ask/cancel for each booking.

Bias: never eat a violation. The cancel path must be more reliable than the
booking path — hence immediate cancel inside T-4h, auto-cancel at T-3h when
Byron hasn't replied (still an hour of margin on the 2-hour deadline), and
the §4.4 phone-the-pro-shop fail-safe when the API cancel fails.
"""

import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import config
import foreup
import gcal
import notify
import store
import weather

logger = logging.getLogger(__name__)


def run() -> dict:
    prefs = store.get_preferences()
    results = []
    for booking in store.active_bookings():
        try:
            results.append(_check_booking(booking, prefs))
        except Exception as e:
            # One bad booking must not stop the others — and an unmanageable
            # booking gets flagged at detection time, not at T-2h (§4.4).
            logger.exception("Watchdog failed on %s", booking["reservation_id"])
            notify.send(f"⚠️ Watchdog can't auto-manage {booking.get('tee_time_display', '?')}: {e}. "
                        f"Manage it manually.", critical=True)
            results.append({"reservation_id": booking["reservation_id"], "action": "error"})
    store.heartbeat("watchdog")  # written last; staleness monitor alerts (§4.4)
    return {"checked": len(results), "results": results}


def _check_booking(booking: dict, prefs: dict) -> dict:
    rid = booking["reservation_id"]
    # Firestore returns timestamps as UTC; weather/calendar checks need local time.
    tee_time = booking["tee_time"].astimezone(ZoneInfo(config.LOCAL_TZ))
    hours_to_tee = (tee_time - datetime.now(timezone.utc)).total_seconds() / 3600

    if hours_to_tee < 0:
        store.update_booking(rid, {"status": store.PLAYED})
        return {"reservation_id": rid, "action": "archived"}

    # Pending ask-first cancel that Byron never answered → auto-cancel at T-3h (§4.3)
    if booking["status"] == store.CANCEL_PENDING:
        if hours_to_tee <= prefs["auto_cancel_at_hours"]:
            return _cancel(booking, f"no reply by T-{prefs['auto_cancel_at_hours']}h "
                                    f"({booking.get('trip_reason', 'check tripped')})")
        return {"reservation_id": rid, "action": "awaiting_reply"}

    reasons = weather.check(tee_time, prefs["weather"])
    try:
        cal = gcal.conflicts(tee_time, prefs["travel_buffer_minutes"], prefs["round_duration_hours"])
        reasons += [f"Calendar conflict: {c}" for c in cal]
    except Exception as e:
        logger.warning("Calendar check failed: %s", e)
        store.audit("watchdog.calendar_error", {"error": str(e)})

    if not reasons:
        return {"reservation_id": rid, "action": "ok"}
    reason_text = "; ".join(reasons)

    if hours_to_tee <= prefs["ask_first_cutoff_hours"]:
        # Inside T-4h: margin beats courtesy — cancel now, notify after (§4.3).
        return _cancel(booking, reason_text)

    store.update_booking(rid, {"status": store.CANCEL_PENDING, "trip_reason": reason_text})
    notify.send(
        f"⚠️ {reason_text} at {booking['tee_time_display']}. "
        f"Keep: {notify.action_link(rid, 'keep')} — "
        f"auto-cancels at T-{prefs['auto_cancel_at_hours']}h if no response."
    )
    return {"reservation_id": rid, "action": "ask_first", "reasons": reasons}


def _cancel(booking: dict, reason: str) -> dict:
    rid = booking["reservation_id"]
    display = booking.get("tee_time_display", rid)

    if booking.get("status") == store.DRY_RUN or str(rid).startswith("dryrun-"):
        store.update_booking(rid, {"status": store.CANCELED, "cancel_reason": reason})
        notify.send(f"🧪 DRY RUN — would have canceled {display} ({reason})")
        return {"reservation_id": rid, "action": "dry_run_cancel"}

    if foreup.cancel(rid):
        store.update_booking(rid, {"status": store.CANCELED, "cancel_reason": reason})
        if booking.get("calendar_event_id"):
            gcal.delete_tee_event(booking["calendar_event_id"])
        notify.send(f"✅ Canceled {display} — {reason}. "
                    f"Check for the ForeUp confirmation email (§2.3).")
        return {"reservation_id": rid, "action": "canceled"}

    # §4.4: the insurance policy.
    store.update_booking(rid, {"status": store.CANCEL_FAILED, "cancel_reason": reason})
    notify.page_cancel_failure(booking)
    return {"reservation_id": rid, "action": "cancel_failed_paged"}
