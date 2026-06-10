"""Sniper (§3): grab the best slot the moment the release window opens.

Invoked by Cloud Scheduler at T-60s before release time. Polls every 2–3
seconds for up to 5 minutes, books the highest-scoring slot immediately
(speed > deliberation), then notifies. Polite outside the release minute —
no sub-second hammering (§0).
"""

import logging
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import config
import foreup
import gcal
import notify
import scoring
import store

logger = logging.getLogger(__name__)

POLL_SECONDS = (2, 3)       # §3.2: every 2–3 seconds
MAX_POLL_MINUTES = 5        # then give up and notify "nothing matched"


def run() -> dict:
    """One snipe attempt. Returns a result dict for the HTTP response/logs."""
    prefs = store.get_preferences()
    tz = ZoneInfo(config.LOCAL_TZ)
    now = datetime.now(tz)
    target_date = (now + timedelta(days=prefs["release_days_ahead"])).date()

    day_name = target_date.strftime("%a")
    if day_name not in prefs["days"]:
        return {"result": "skipped", "reason": f"{day_name} not in preferred days"}

    week_key = f"{target_date.isocalendar().year}-W{target_date.isocalendar().week:02d}"
    if store.bookings_for_week(week_key) >= prefs["max_bookings_per_week"]:
        return {"result": "skipped", "reason": "weekly booking cap reached (§3.2)"}
    if any(b.get("date") == str(target_date) for b in store.active_bookings()):
        return {"result": "skipped", "reason": "already hold a booking that day (§3.2)"}

    courses = _courses_with_ids(prefs)
    if not courses:
        return {"result": "error", "reason": "No schedule_ids configured — finish §2.1 discovery"}

    foreup.login()  # §3.2 pre-auth: token fresh before the release moment
    store.audit("snipe.start", {"target_date": str(target_date), "dry_run": prefs["dry_run"]})

    deadline = time.monotonic() + MAX_POLL_MINUTES * 60
    date_param = target_date.strftime("%m-%d-%Y")
    while time.monotonic() < deadline:
        slots = []
        for course, schedule_id in courses.items():
            try:
                for raw in foreup.get_times(schedule_id, date_param, prefs["players"], prefs["holes"]):
                    slot_time = _parse_slot_time(raw, tz)
                    if slot_time:
                        slots.append({"time": slot_time, "course": course, "raw": raw})
            except foreup.ForeUpError as e:
                logger.warning("get_times %s: %s", course, e)  # keep polling other courses

        choice = scoring.best(slots, prefs)
        if choice:
            return _book(choice, prefs, target_date, week_key)
        time.sleep(random.uniform(*POLL_SECONDS))

    notify.send(f"⛳ Snipe for {target_date} found nothing in your window "
                f"{prefs['time_window'][0]}–{prefs['time_window'][1]}.")
    store.audit("snipe.no_match", {"target_date": str(target_date)})
    return {"result": "no_match", "target_date": str(target_date)}


def _book(choice: dict, prefs: dict, target_date, week_key: str) -> dict:
    display = f"{choice['course']} {choice['time'].strftime('%a %-m/%-d %-I:%M %p')}"

    if prefs["dry_run"]:
        store.save_booking({
            "reservation_id": f"dryrun-{int(time.time())}",
            "status": store.DRY_RUN,
            "course": choice["course"],
            "tee_time": choice["time"],
            "tee_time_display": display,
            "date": str(target_date),
            "week_key": week_key,
        })
        notify.send(f"🧪 DRY RUN — would have booked: {display}")
        return {"result": "dry_run", "slot": display}

    reservation_id = foreup.book(choice["raw"], prefs["players"])
    event_id = gcal.create_tee_event(choice["course"], choice["time"], prefs["round_duration_hours"])
    store.save_booking({
        "reservation_id": reservation_id,
        "course": choice["course"],
        "tee_time": choice["time"],
        "tee_time_display": display,
        "date": str(target_date),
        "week_key": week_key,
        "players": prefs["players"],
        "calendar_event_id": event_id,
    })
    notify.send(f"⛳ Booked: {display} for {prefs['players']}. "
                f"Cancel: {notify.action_link(reservation_id, 'cancel')}")
    return {"result": "booked", "reservation_id": reservation_id, "slot": display}


def _courses_with_ids(prefs: dict) -> dict:
    """Preferred courses (in rank order) that have a discovered schedule_id."""
    return {
        course: config.COURSE_SCHEDULE_IDS[course]
        for course in prefs["courses_priority"]
        if config.COURSE_SCHEDULE_IDS.get(course)
    }


def _parse_slot_time(raw: dict, tz) -> datetime | None:
    """ForeUp `time` is typically 'YYYY-MM-DD HH:MM' local. Verify in §2.1."""
    try:
        return datetime.strptime(raw["time"], "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    except (KeyError, ValueError):
        logger.warning("Unparseable slot time: %r", raw.get("time"))
        return None
