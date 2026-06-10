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


@app.get("/times")
def times():
    """Live availability viewer: what the sniper would see (and how it scores
    each slot). Usage: /times?date=YYYY-MM-DD&token=...  Date defaults to the
    next release-window day (today + 3)."""
    _require_scheduler_token()
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    import scoring
    import sniper

    prefs = store.get_preferences()
    tz = ZoneInfo(config.LOCAL_TZ)
    date_str = request.args.get("date") or str((datetime.now(tz) + timedelta(days=prefs["release_days_ahead"])).date())
    target = datetime.strptime(date_str, "%Y-%m-%d").date()

    courses = {c: sid for c, sid in config.COURSE_SCHEDULE_IDS.items() if sid}
    body, errors = [], []
    if not courses:
        errors.append("No schedule_ids configured yet — finish the §2.1 ForeUp capture first.")
    for course, schedule_id in courses.items():
        try:
            import foreup
            for raw in foreup.get_times(schedule_id, target.strftime("%m-%d-%Y"),
                                        prefs["players"], prefs["holes"]):
                slot_time = sniper._parse_slot_time(raw, tz)
                if not slot_time:
                    continue
                s = scoring.score(slot_time, course, prefs)
                body.append((slot_time, course, s))
        except Exception as e:
            errors.append(f"{course}: {e}")

    body.sort(key=lambda r: (-(r[2] if r[2] is not None else -9999), r[0]))
    logger.info("TIMES VIEW %s: %d slots, errors=%s, top=%s", date_str, len(body), errors,
                [(t.strftime('%H:%M'), c, s) for t, c, s in body[:5]])
    rows = "".join(
        f"<tr><td><strong>{t.strftime('%-I:%M %p')}</strong></td><td>{c}</td>"
        f"<td>{'—' if s is None else f'{s:.0f}'}</td>"
        f"<td>{'<span class=pill style=background:#dcf3e3;color:#1f5c34>would book</span>' if i == 0 and s is not None else ''}</td></tr>"
        for i, (t, c, s) in enumerate(body)
    )
    err_html = "".join(f"<div class='empty flag'>{e}</div>" for e in errors)
    table = (f"<table><tr><th>Time</th><th>Course</th><th>Score</th><th></th></tr>{rows}</table>"
             if rows else "<div class='empty'>No open slots returned.</div>")
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>tee-agent · availability</title><style>{STATUS_CSS}</style></head><body>
<header><h1>⛳ availability</h1>
<span style='margin-left:auto;font-size:13px;opacity:.85'>{target.strftime('%A %b %-d')} ·
window {prefs['time_window'][0]}–{prefs['time_window'][1]}</span></header>
<main>{err_html}<div class='card'>{table}</div>
<footer>Score = course rank + closeness to ideal time ({prefs['ideal_time']}); '—' = outside
your window. Change date with <code>?date=YYYY-MM-DD</code>.</footer></main></body></html>"""


@app.route("/discover", methods=["GET", "POST"])
def discover():
    """One-shot §2.1 discovery probe (see discover.py). Remove once configured."""
    _require_scheduler_token()
    import json
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    import discover as discover_mod

    date_str = (datetime.now(ZoneInfo(config.LOCAL_TZ)) + timedelta(days=2)).strftime("%m-%d-%Y")
    result = discover_mod.run(request.args.get("date", date_str))
    logger.info("DISCOVERY RESULT: %s", json.dumps(result)[:60000])
    return result


@app.post("/booking-test")
def booking_test():
    """§2.3 one-shot: book + immediately cancel a throwaway slot. Remove after."""
    _require_scheduler_token()
    import json
    import discover as discover_mod

    date_str = request.args.get("date", "")
    result = discover_mod.booking_test(date_str)
    logger.info("BOOKING TEST RESULT: %s", json.dumps(result)[:60000])
    return result


@app.route("/reservations", methods=["GET", "POST"])
def reservations():
    """Raw account reservations from ForeUp — state reconciliation check."""
    _require_scheduler_token()
    import foreup
    status_code, body = foreup.list_reservations()
    logger.info("RESERVATIONS CHECK: status=%s body=%s", status_code, body[:5000])
    return {"foreup_status": status_code, "body": body[:5000]}


@app.get("/")
def index():
    return f"""<!doctype html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>tee-agent</title><style>{STATUS_CSS}</style></head><body>
<header><h1>⛳ tee-agent</h1></header>
<main><div class='card'><div class='empty'>
Fargo tee time sniper is running.<br><br>
Bookings dashboard: <code>/status?token=…</code> (token required)
</div></div></main></body></html>"""


@app.get("/healthz")
def healthz():
    return {"ok": True}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)), debug=False)
