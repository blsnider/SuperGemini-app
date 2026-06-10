# ⛳ tee-agent — Fargo Tee Time Sniper + Watchdog

Books Fargo Park District tee times the moment they release (3 days ahead) and
auto-cancels on weather or calendar conflicts — always before the 2-hour
cancellation deadline. Full design: [PLAN.md](PLAN.md).

**Personal use only.** Polite request rates, no resale, stops if the Park
District objects (PLAN §8).

## Status: scaffold complete, blocked on discovery

The code is structured around PLAN.md but **cannot go live** until the manual
Phase 1 discovery (§2.1) is done in a browser. `grep -rn "TODO(discovery"` for
the exact gaps:

| Blocker | Where to fill in |
|---|---|
| Login endpoint/payload, JWT location, CAPTCHA? | `foreup.py::login`, `config.py` |
| `schedule_id` per course + `booking_class` | `config.py::COURSE_SCHEDULE_IDS` |
| Hold/commit/cancel payloads | `foreup.py::book/cancel` |
| Exact release clock time (§0 — Phase 2 blocker) | `deploy/setup.sh::SNIPE_CRON`, Firestore prefs |
| Course/day/time preferences, weather thresholds | Firestore `tee_agent_config/preferences` |
| Byron's phone + Twilio creds | Secret Manager + `TEE_AGENT_PHONE` env |

## Module map

| File | PLAN section | Purpose |
|---|---|---|
| `app.py` | §1 | Flask routes: `/snipe`, `/watchdog`, `/confirm/<id>`, `/status` |
| `foreup.py` | §2 | Thin ForeUp client — login, times, two-step book, cancel w/ retries |
| `sniper.py` | §3 | Release-window polling (2–3s, 5 min max), scoring, booking caps |
| `scoring.py` | §3.3 | Course rank + ideal-time proximity |
| `watchdog.py` | §4 | Weather/calendar checks, ask-first flow, T-3h auto-cancel |
| `weather.py` | §4.2 | Open-Meteo primary, NWS backup |
| `gcal.py` | §4.2 | Calendar conflicts + ⛳ event creation |
| `notify.py` | §5 | Twilio SMS → SendGrid fallback; §4.4 pro-shop pager |
| `store.py` | §1 | Firestore: bookings, prefs, audit, heartbeat, violations |
| `deploy/setup.sh` | §1 | Cloud Run + 2 Scheduler jobs + secrets + dead-watchdog alert |

## Safety design (the part that matters — PLAN §4.4)

- **Dry-run is the default.** The sniper logs/SMSes what it *would* book until
  `dry_run: false` is set in Firestore. Run a few release windows that way first.
- Cancel path: 3 retries w/ backoff → on failure, **immediately SMS Byron the
  pro shop phone number** for that course.
- Ask-first cancels auto-execute at **T-3h** with no reply (1h margin on the
  2h deadline); checks tripping inside T-4h cancel immediately, notify after.
- Watchdog writes a Firestore heartbeat after every run; the Scheduler-failure
  alert in `deploy/setup.sh` catches a silently dead watchdog.
- Max 1 booking/day, 2/week (configurable) — no hoarding.

## Local dev

```bash
cd tee-agent
pip install -r requirements.txt
export GCP_PROJECT=sis-sandbox-463113 FOREUP_USERNAME=... FOREUP_PASSWORD=...
python app.py   # needs ADC for Firestore: gcloud auth application-default login
```

## Build order (PLAN §6)

1. **Phase 1 (manual):** DevTools capture per §2.1 → fill the TODOs → test a
   real throwaway weekday booking + cancel via `foreup.py` in a REPL.
2. **Phase 2:** `deploy/setup.sh`, confirm release time, watch dry-run snipes.
3. **Phase 3:** flip `dry_run: false`; simulate bad weather by tightening
   thresholds in Firestore against a real booking.
4. **Phase 4:** violation counter is wired (`store.record_violation`) — add a
   weekly summary message and `/status` polish.
