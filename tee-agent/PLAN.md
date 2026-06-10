# Fargo Tee Time Agent — PLAN.md

Automated system to book Fargo Park District tee times the moment they release (3 days ahead), and auto-cancel bookings when weather or calendar conflicts arise — always before the 2-hour cancellation deadline.

**Owner:** Byron
**Target runtime:** GCP Cloud Run (project: `sis-sandbox-463113`) + Cloud Scheduler
**Booking platform:** ForeUp (foreupsoftware.com), supplemented by Noteefy reminders

---

## 0. Hard Constraints (read first)

- **Release window:** Tee times open **3 days in advance**. Weekend slots go fast — the sniper must fire within seconds of release.
  - ⚠️ TODO: Confirm the exact *clock time* times release (midnight? 6 AM? 7 PM?). Call the pro shop or watch the site at midnight on a Wednesday for a Saturday date. The entire sniper schedule depends on this.
- **Cancellation policy:** Must cancel or adjust player count **≥ 2 hours** before tee time. Two violations in a season = loss of online booking privileges (phone-only, prepaid). **The bot must be more reliable at canceling than at booking.** Bias every design decision toward "never eat a violation."
- **Unofficial API:** ForeUp has no public API. We use the same JSON endpoints the website uses. These can change without notice — build with good error alerting, not silent failure.
- **Be polite:** No sub-second hammering. Poll at human-ish rates except in the ~60s around release time.

## 1. Architecture

```
┌─────────────────────────────────────────────────┐
│ Cloud Run service: tee-agent (Flask, 1 instance)│
│                                                 │
│  /snipe        ← Cloud Scheduler @ release time │
│  /watchdog     ← Cloud Scheduler every 30 min   │
│  /confirm/<id> ← link in SMS/email for approvals│
│  /status       ← simple dashboard of bookings   │
└─────────────────────────────────────────────────┘
        │                │               │
   ForeUp API      Open-Meteo /     Google Calendar
   (book/cancel)   NWS forecast     API (conflicts)
        │
   Firestore (state: bookings, preferences, violation log)
        │
   Notifications: SMS via Twilio (or email via SendGrid)
```

Single Cloud Run service, min-instances=0, two Scheduler jobs. State in Firestore (cheap, no SQL needed). Secrets (ForeUp credentials, Twilio keys) in GCP Secret Manager — same pattern as SuperGemini.

## 2. ForeUp API Integration

### 2.1 Discovery tasks (do these first, manually, in a browser)
1. Log into the Fargo ForeUp booking site. Open DevTools → Network tab.
2. Capture from the login request: endpoint URL, payload shape, and the JWT returned (usually in a `Set-Cookie` or response body field `jwt`).
3. Make (and then cancel) one real booking far in the future. Capture:
   - `GET .../times` request: note `schedule_id` (one per course — there are 5 Fargo courses), `booking_class`, date param format, and response shape.
   - `POST .../pending_reservation` then `POST .../users/reservations` (typical ForeUp two-step: hold, then commit). Capture exact payloads.
   - `DELETE` or cancel endpoint + payload.
4. Record whether login has CAPTCHA. If yes → fall back to long-lived session token captured manually and refreshed monthly, stored in Secret Manager.
5. Note whether booking required prepayment or card selection. If prepay, capture the payment payload too (or restrict bot to pay-at-course courses).

### 2.2 Client module (`foreup.py`)
- `login() -> token` with retry + token caching (Firestore, with expiry).
- `get_times(schedule_id, date, players) -> [slots]`
- `book(slot, players) -> reservation_id` (two-step hold/commit)
- `cancel(reservation_id) -> bool` with **3 retries, exponential backoff**; on final failure, page Byron immediately (see §5).
- All calls log to Firestore for audit.

### 2.3 Things to verify with a test booking
- Does an API-made booking still trigger Noteefy reminders (48h/24h/3h)? Does *not* confirming via Noteefy cause any problem?
- Does cancellation via API register correctly (check email confirmation arrives)?
- Player-count modification endpoint (needed to avoid the "fewer players showed" violation).

## 3. Sniper (booking) Logic

### 3.1 Trigger
- Cloud Scheduler hits `/snipe` daily at **T-60s before release time** (TODO from §0).
- Service computes target date = today + 3 days. Skips if target date's day-of-week isn't in Byron's preference list.

### 3.2 Behavior
1. Pre-auth: refresh ForeUp token before release moment.
2. At release: poll `get_times` every **2–3 seconds for up to 5 minutes** (then give up and notify "nothing matched").
3. Score available slots against preferences (see §3.3); book the highest-scoring slot immediately. Speed > deliberation on weekends.
4. On success: write booking to Firestore, create a Google Calendar event ("⛳ North Fargo 8:10 AM — booked by tee-agent"), send SMS confirmation.
5. Never hold more than **one reservation per day** and configurable max per week (default 2) — avoids hoarding and violation exposure.

### 3.3 Preferences (config in Firestore, editable without redeploy)
```yaml
# TODO Byron: fill these in
courses_priority: [Edgewood?, Rose Creek?, Osgood?, El Zagal?, Prairiewood?]  # which of the 5, ranked
days: [Sat, Sun]            # which days to snipe
time_window: ["07:00", "10:30"]
players: 2                   # and names/guests handling?
holes: 18
sweeteners: prefer earlier? prefer specific course over earlier time?
```
Scoring = course rank weight + proximity to ideal time. Define ideal time per day.

## 4. Watchdog (auto-cancel) Logic

### 4.1 Trigger
- Cloud Scheduler hits `/watchdog` **every 30 minutes**. For each active booking:

### 4.2 Checks
1. **Weather** (Open-Meteo, free, no key; NWS as backup):
   - Forecast at tee time for Fargo coordinates.
   - Default thresholds (TODO Byron — tune): precip probability > 60%, sustained wind > 25 mph, temp < 45°F, or any thunderstorm code.
2. **Calendar** (Google Calendar API, read-only on Byron's calendar):
   - Any non-tee-time event overlapping [tee time − travel buffer, tee time + 4.5h for 18 holes].

### 4.3 Cancel decision flow — ASK-FIRST mode (default)
- If a check trips **and** time-to-tee > 4 hours: SMS Byron — "Rain 80% at Sat 8:10 AM Rose Creek. Reply CANCEL or tap link to keep. Auto-cancels at T-3h if no response."
- If no response by **T-3 hours**: auto-cancel (still 1 hour of margin before the deadline).
- If a check trips **inside T-4h**: cancel immediately, notify after. Margin beats courtesy.
- Manual override: `/status` page lists bookings with Keep/Cancel buttons.

### 4.4 Fail-safe (most important section in this file)
- Cancel API failure after retries → **immediately SMS + email Byron** with the pro shop phone number for that course so he can cancel by phone within the window.
- Watchdog also self-monitors: if a scheduled run doesn't complete (heartbeat doc in Firestore), a separate lightweight Cloud Function alerts Byron. A silent dead watchdog is how violations happen.
- Booking that can't be auto-managed (e.g., token expired) → flag in SMS at time of detection, not at T-2h.

## 5. Notifications
- Twilio SMS (or email-to-SMS gateway as zero-cost alt) for: booking made, cancel pending approval, canceled, **any failure**.
- Every message includes course name, date/time, and a one-tap action link.

## 6. Build Phases

**Phase 1 — Discovery & manual client (1 session)**
- Capture endpoints (§2.1). Write `foreup.py`. Test login, list times, book + cancel a real throwaway weekday slot. Verify email confirmations + Noteefy behavior.

**Phase 2 — Sniper MVP (1 session)**
- Flask app + `/snipe`, preference scoring, Firestore state, deploy to Cloud Run, one Scheduler job. Dry-run mode flag (logs the slot it *would* book) for the first few release windows.

**Phase 3 — Watchdog (1 session)**
- Weather + calendar checks, ask-first SMS flow, fail-safe alerting, second Scheduler job. Test by booking a slot and simulating bad weather thresholds.

**Phase 4 — Hardening**
- Token refresh edge cases, violation counter (track Fargo's 2-strike status in Firestore), `/status` page, weekly summary message.

## 7. Open TODOs for Byron
- [ ] Exact release clock time (§0) — blocker for Phase 2
- [ ] Course priority list + day/time preferences (§3.3)
- [ ] Weather thresholds (§4.2)
- [ ] CAPTCHA / prepayment answers from discovery (§2.1)
- [ ] Twilio account or preferred SMS path
- [ ] Confirm Calendar API access OK on personal calendar

## 8. Risks
- ForeUp endpoint changes → alerting on any non-200, keep client thin and fixable.
- Terms-of-service gray area: this books for personal use only, no resale, polite request rates. If the Park District objects, stop.
- Two-strike policy: the watchdog fail-safe (§4.4) is the insurance policy. Test it deliberately before trusting the system on a weekend booking.
