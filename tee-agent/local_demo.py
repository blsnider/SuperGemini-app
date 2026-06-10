"""Run tee-agent locally with NO GCP dependencies, for UI preview and
endpoint smoke tests.

Stubs the Firestore layer with in-memory dicts (seeded with realistic
bookings so /status looks like a live system) and stubs secrets. Real
deploys never import this file.

Usage:  .venv/bin/python local_demo.py   # serves on :8080, token 'demo'
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import config
import store

TZ = ZoneInfo(config.LOCAL_TZ)
_now = datetime.now(TZ)

# ---- in-memory store stubs -------------------------------------------------
_prefs = dict(config.DEFAULT_PREFERENCES)
_bookings: dict[str, dict] = {}
_audit: list[dict] = []
_heartbeats: dict[str, dict] = {}


def _seed():
    sat = (_now + timedelta(days=(5 - _now.weekday()) % 7 or 7)).replace(
        hour=8, minute=10, second=0, microsecond=0)
    sun = sat + timedelta(days=1, minutes=30)
    _bookings["10482913"] = {
        "reservation_id": "10482913", "status": store.ACTIVE,
        "course": "Edgewood", "tee_time": sat,
        "tee_time_display": f"Edgewood {sat.strftime('%a %-m/%-d %-I:%M %p')}",
        "date": str(sat.date()), "week_key": "demo", "players": 2,
    }
    _bookings["10482977"] = {
        "reservation_id": "10482977", "status": store.CANCEL_PENDING,
        "course": "Rose Creek", "tee_time": sun,
        "tee_time_display": f"Rose Creek {sun.strftime('%a %-m/%-d %-I:%M %p')}",
        "date": str(sun.date()), "week_key": "demo", "players": 2,
        "trip_reason": "Rain 80%; Wind 28 mph",
    }


store.get_preferences = lambda: dict(_prefs)
store.save_booking = lambda b: _bookings.__setitem__(str(b["reservation_id"]), b) or str(b["reservation_id"])
store.update_booking = lambda rid, f: _bookings[str(rid)].update(f)
store.get_booking = lambda rid: _bookings.get(str(rid))
store.active_bookings = lambda: [
    dict(b) for b in _bookings.values()
    if b["status"] in (store.ACTIVE, store.CANCEL_PENDING)
]
store.bookings_for_week = lambda wk: sum(
    1 for b in _bookings.values()
    if b.get("week_key") == wk and b["status"] != store.CANCELED)
store.audit = lambda event, detail=None: _audit.append({"event": event, "detail": detail})
store.heartbeat = lambda name="watchdog": _heartbeats.__setitem__(name, {"last_run": datetime.now(timezone.utc)})
store.db = lambda: (_ for _ in ()).throw(RuntimeError("no Firestore in local demo"))

config.load_secret = lambda name, project_id=None: {
    "tee-agent-scheduler-token": "demo",
    "tee-agent-confirm-secret": "demo-confirm",
}.get(name)

_seed()

# Import AFTER stubbing so app.py binds the stubbed functions' module attrs.
import app as tee_app  # noqa: E402

# gcal needs real creds; stub it for local watchdog runs (no conflicts).
import watchdog  # noqa: E402
watchdog.gcal.conflicts = lambda *a, **k: []

if __name__ == "__main__":
    print("tee-agent local demo on http://127.0.0.1:8080  (token: demo)")
    print("  /status?token=demo   /healthz   POST /watchdog  POST /snipe")
    tee_app.app.run(host="127.0.0.1", port=8080)
