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


STATUS_CSS = """
:root { --green: #2e7d46; --ink: #1c2b22; }
* { box-sizing: border-box; }
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; margin: 0;
       background: #eef3ee; color: var(--ink); }
header { background: linear-gradient(135deg, #1f5c34, #2e7d46); color: #fff;
         padding: 22px 28px; display: flex; align-items: baseline; gap: 14px; }
header h1 { margin: 0; font-size: 22px; font-weight: 700; }
.badge { font-size: 12px; font-weight: 700; letter-spacing: .06em;
         padding: 4px 10px; border-radius: 999px; background: #ffb74d; color: #5a3a00; }
.badge.live { background: #a5e8b8; color: #114d27; }
main { max-width: 860px; margin: 28px auto; padding: 0 20px; }
.card { background: #fff; border-radius: 12px; box-shadow: 0 2px 10px rgba(28,43,34,.08);
        overflow: hidden; }
table { width: 100%; border-collapse: collapse; font-size: 15px; }
th { text-align: left; font-size: 12px; text-transform: uppercase; letter-spacing: .05em;
     color: #6b7d70; padding: 14px 18px; border-bottom: 2px solid #e3ece5; }
td { padding: 14px 18px; border-bottom: 1px solid #eef3ee; }
tr:last-child td { border-bottom: 0; }
.pill { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 999px; }
.pill.active { background: #dcf3e3; color: #1f5c34; }
.pill.cancel_pending { background: #fdeccd; color: #8a5600; }
.pill.cancel_failed { background: #fbd9d3; color: #93291c; }
.flag { color: #b3541e; font-size: 14px; }
.actions a { text-decoration: none; font-weight: 600; font-size: 14px;
             padding: 6px 14px; border-radius: 8px; }
.actions a.keep { color: #1f5c34; background: #e7f5ec; margin-right: 6px; }
.actions a.cancel { color: #93291c; background: #fdeeec; }
.empty { padding: 40px; text-align: center; color: #6b7d70; }
footer { color: #6b7d70; font-size: 13px; margin-top: 14px; }
footer code { background: #e3ece5; padding: 1px 6px; border-radius: 4px; }
"""


@app.get("/status")
def status():
    _require_scheduler_token()
    rows = []
    for b in store.active_bookings():
        rid = b["reservation_id"]
        status_cls = b.get("status", "active")
        rows.append(
            f"<tr><td><strong>{b.get('tee_time_display', '?')}</strong></td>"
            f"<td><span class='pill {status_cls}'>{status_cls.replace('_', ' ')}</span></td>"
            f"<td class='flag'>{b.get('trip_reason', '—') or '—'}</td>"
            f"<td class='actions'>"
            f"<a class='keep' href='/confirm/{rid}?action=keep&sig={sign(rid)}'>Keep</a>"
            f"<a class='cancel' href='/confirm/{rid}?action=cancel&sig={sign(rid)}'>Cancel</a>"
            f"</td></tr>"
        )
    prefs = store.get_preferences()
    dry = prefs["dry_run"]
    table = (
        "<table><tr><th>Tee time</th><th>Status</th><th>Flag</th><th></th></tr>"
        + "".join(rows) + "</table>"
        if rows else "<div class='empty'>No active bookings — the sniper fires at the next release window.</div>"
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>tee-agent</title><style>{STATUS_CSS}</style></head><body>
<header><h1>⛳ tee-agent</h1>
<span class='badge {'live' if not dry else ''}'>{'LIVE' if not dry else 'DRY RUN'}</span>
<span style='margin-left:auto;font-size:13px;opacity:.85'>Fargo Park District ·
window {prefs['time_window'][0]}–{prefs['time_window'][1]}</span></header>
<main><div class='card'>{table}</div>
<footer>{len(rows)} active booking(s) · watchdog heartbeat:
<code>tee_agent_heartbeats/watchdog</code> · cancel deadline 2h before tee time</footer>
</main></body></html>"""


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False)
