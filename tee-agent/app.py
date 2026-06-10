"""tee-agent Flask entrypoint (§1).

Routes:
  POST /snipe         Cloud Scheduler, fired at T-60s before release time
  POST /watchdog      Cloud Scheduler, every 30 minutes
  GET  /confirm/<id>  one-tap keep/cancel links from SMS (HMAC-signed)
  GET  /status        dashboard of bookings with Keep/Cancel buttons
  GET  /healthz       unauthenticated liveness check

Scheduler routes require the shared token (Secret Manager:
`tee-agent-scheduler-token`) in the X-TeeAgent-Token header; the Scheduler
jobs are created with it in deploy/setup.sh.
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone

from flask import Flask, abort, request

import config
import notify
import sniper
import store
import watchdog
from watchdog import _cancel as cancel_booking

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_scheduler_token = None
_confirm_secret = None


def _require_scheduler_token():
    global _scheduler_token
    if _scheduler_token is None:
        _scheduler_token = config.load_secret("tee-agent-scheduler-token") or ""
    supplied = request.headers.get("X-TeeAgent-Token", "") or request.args.get("token", "")
    if not _scheduler_token or not hmac.compare_digest(supplied, _scheduler_token):
        abort(403)


def sign(reservation_id: str) -> str:
    global _confirm_secret
    if _confirm_secret is None:
        _confirm_secret = config.load_secret("tee-agent-confirm-secret") or "dev-only"
    return hmac.new(_confirm_secret.encode(), str(reservation_id).encode(),
                    hashlib.sha256).hexdigest()[:20]


# SMS links can't carry headers, so action links embed the HMAC signature.
notify.action_link = lambda rid, action: (
    f"{notify.BASE_URL}/confirm/{rid}?action={action}&sig={sign(rid)}"
)


@app.post("/snipe")
def snipe():
    _require_scheduler_token()
    result = sniper.run()
    logger.info("Snipe result: %s", result)
    return result


@app.post("/watchdog")
def run_watchdog():
    _require_scheduler_token()
    result = watchdog.run()
    logger.info("Watchdog result: %s", result)
    return result


@app.get("/confirm/<reservation_id>")
def confirm(reservation_id: str):
    if not hmac.compare_digest(request.args.get("sig", ""), sign(reservation_id)):
        abort(403)
    booking = store.get_booking(reservation_id)
    if not booking:
        abort(404)
    booking["reservation_id"] = reservation_id
    action = request.args.get("action", "keep")

    if action == "cancel":
        result = cancel_booking(booking, "manual cancel via link")
        return f"<h2>Cancel: {result['action']}</h2>"
    # keep: clear any pending auto-cancel
    if booking.get("status") == store.CANCEL_PENDING:
        store.update_booking(reservation_id, {"status": store.ACTIVE, "kept_at": datetime.now(timezone.utc)})
        store.audit("confirm.keep", {"reservation_id": reservation_id})
    return f"<h2>Keeping {booking.get('tee_time_display', reservation_id)} ⛳</h2>"


@app.get("/status")
def status():
    _require_scheduler_token()
    rows = []
    for b in store.active_bookings():
        rid = b["reservation_id"]
        rows.append(
            f"<tr><td>{b.get('tee_time_display', '?')}</td><td>{b.get('status')}</td>"
            f"<td>{b.get('trip_reason', '')}</td>"
            f"<td><a href='/confirm/{rid}?action=keep&sig={sign(rid)}'>Keep</a> | "
            f"<a href='/confirm/{rid}?action=cancel&sig={sign(rid)}'>Cancel</a></td></tr>"
        )
    prefs = store.get_preferences()
    return (
        f"<h1>⛳ tee-agent {'(DRY RUN)' if prefs['dry_run'] else ''}</h1>"
        "<table border=1 cellpadding=6><tr><th>Tee time</th><th>Status</th>"
        "<th>Flag</th><th>Actions</th></tr>" + "".join(rows) + "</table>"
        f"<p>{len(rows)} active booking(s). Watchdog heartbeat in Firestore "
        "<code>tee_agent_heartbeats/watchdog</code>.</p>"
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False)
