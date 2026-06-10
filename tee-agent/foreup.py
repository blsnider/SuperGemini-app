"""Thin ForeUp client (§2.2).

ForeUp has no public API — these are the same JSON endpoints the booking
website uses, captured manually per §2.1. They can change without notice, so
every call audits to Firestore and raises ForeUpError loudly on any non-200
rather than failing silently.

TODO(discovery §2.1): every endpoint path and payload below is the *typical*
ForeUp shape and must be verified against the captured DevTools traffic
before going live. Grep for "TODO(discovery" to find them all.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

import requests

import config
import store

logger = logging.getLogger(__name__)

TOKEN_DOC = "foreup_token"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) tee-agent/0.1 (personal use)"


class ForeUpError(Exception):
    """Any unexpected ForeUp response. Alert, don't swallow."""


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
    return s


def login() -> str:
    """Return a JWT, using the cached Firestore token if still fresh.

    If discovery (§2.1) finds a CAPTCHA on login, replace this with reading a
    manually captured long-lived token from Secret Manager (`foreup-session-token`)
    and alert when it nears expiry.
    """
    doc = store.db().collection("tee_agent_config").document(TOKEN_DOC)
    snap = doc.get()
    if snap.exists:
        cached = snap.to_dict()
        if cached.get("expires_at") and cached["expires_at"] > datetime.now(timezone.utc):
            return cached["jwt"]

    username = config.load_secret("foreup-username")
    password = config.load_secret("foreup-password")
    if not username or not password:
        raise ForeUpError("ForeUp credentials missing from Secret Manager")

    # TODO(discovery §2.1): verify payload field names and where the JWT is
    # returned (response body `jwt` vs Set-Cookie).
    resp = _session().post(
        config.FOREUP_LOGIN_URL,
        data={
            "username": username,
            "password": password,
            "booking_class_id": config.FOREUP_BOOKING_CLASS,
            "api_key": "no_limits",
        },
        timeout=15,
    )
    store.audit("foreup.login", {"status": resp.status_code})
    if resp.status_code != 200:
        raise ForeUpError(f"Login failed: HTTP {resp.status_code}")
    jwt = resp.json().get("jwt")
    if not jwt:
        raise ForeUpError("Login succeeded but no jwt in response — recheck §2.1 capture")

    doc.set({
        "jwt": jwt,
        # Conservative 12h cache; adjust once the real token TTL is known.
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=12),
    })
    return jwt


def _auth_session() -> requests.Session:
    s = _session()
    s.headers["Api-Key"] = "no_limits"
    s.headers["X-Authorization"] = f"Bearer {login()}"
    return s


def get_times(schedule_id: str, date: str, players: int, holes: int = 18) -> list[dict]:
    """List open slots for one course/date. `date` is MM-DD-YYYY (verify §2.1).

    Returns the raw slot dicts; scoring/filtering happens in sniper.py.
    """
    # TODO(discovery §2.1): confirm param names and date format.
    resp = _auth_session().get(
        f"{config.FOREUP_BASE_URL}/times",
        params={
            "time": "all",
            "date": date,
            "holes": holes,
            "players": players,
            "schedule_id": schedule_id,
            "booking_class": config.FOREUP_BOOKING_CLASS,
            "api_key": "no_limits",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        store.audit("foreup.get_times.error", {"status": resp.status_code, "date": date})
        raise ForeUpError(f"get_times failed: HTTP {resp.status_code}")
    return resp.json()


def book(slot: dict, players: int) -> str:
    """Two-step hold/commit (§2.1). Returns the reservation id."""
    s = _auth_session()

    # TODO(discovery §2.1): verify both payloads against captured traffic.
    hold = s.post(
        f"{config.FOREUP_BASE_URL}/pending_reservation",
        json={"time": slot["time"], "holes": slot.get("holes", 18),
              "players": players, "schedule_id": slot["schedule_id"]},
        timeout=15,
    )
    store.audit("foreup.hold", {"status": hold.status_code, "slot": slot.get("time")})
    if hold.status_code != 200:
        raise ForeUpError(f"Hold failed: HTTP {hold.status_code}")
    reservation_id = hold.json().get("reservation_id")

    commit = s.post(
        f"{config.FOREUP_BASE_URL}/users/reservations",
        json={**slot, "players": players, "pending_reservation_id": reservation_id},
        timeout=15,
    )
    store.audit("foreup.commit", {"status": commit.status_code, "slot": slot.get("time")})
    if commit.status_code != 200:
        raise ForeUpError(f"Commit failed after hold: HTTP {commit.status_code}")
    booked_id = commit.json().get("TTID") or commit.json().get("reservation_id") or reservation_id
    if not booked_id:
        raise ForeUpError("Booking committed but no reservation id found — recheck §2.1")
    return str(booked_id)


def cancel(reservation_id: str) -> bool:
    """Cancel with 3 retries + exponential backoff (§2.2).

    Returns False after the final failure — the CALLER must then fire the
    §4.4 fail-safe (SMS Byron the pro shop number). Never raises past retries,
    so the watchdog loop keeps processing other bookings.
    """
    s = _auth_session()
    for attempt in range(3):
        try:
            # TODO(discovery §2.1): verify method (DELETE vs POST) and path.
            resp = s.delete(
                f"{config.FOREUP_BASE_URL}/users/reservations/{reservation_id}",
                timeout=15,
            )
            store.audit("foreup.cancel", {
                "status": resp.status_code, "reservation_id": reservation_id,
                "attempt": attempt + 1,
            })
            if resp.status_code in (200, 204):
                return True
        except requests.RequestException as e:
            store.audit("foreup.cancel.exception", {"error": str(e), "attempt": attempt + 1})
        time.sleep(2 ** attempt)
    logger.error("Cancel FAILED after retries for %s — fail-safe required", reservation_id)
    return False
