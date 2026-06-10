"""Configuration for tee-agent.

Secrets follow the same Secret Manager pattern as SuperGemini's app.py:
env var first, then GCP Secret Manager in project sis-sandbox-463113.

Runtime preferences (courses, days, time window, thresholds) live in
Firestore (`tee_agent_config/preferences`) so they're editable without a
redeploy — see DEFAULT_PREFERENCES for the document shape and defaults.
"""

import logging
import os

logger = logging.getLogger(__name__)

GCP_PROJECT = os.getenv("GCP_PROJECT", "sis-sandbox-463113")

# Fargo, ND — used for weather forecasts.
FARGO_LAT = 46.8772
FARGO_LON = -96.7898
LOCAL_TZ = "America/Chicago"

# ---------------------------------------------------------------------------
# TODO(discovery §2.1): fill these in after capturing the real endpoints in
# DevTools. Values below are the typical ForeUp shapes and WILL need edits.
# ---------------------------------------------------------------------------
FOREUP_BASE_URL = os.getenv("FOREUP_BASE_URL", "https://foreupsoftware.com/index.php/api/booking")
FOREUP_LOGIN_URL = os.getenv("FOREUP_LOGIN_URL", "https://foreupsoftware.com/index.php/api/booking/users/login")

# TODO(discovery §2.1): one schedule_id per course, from the GET .../times call.
# Order here is irrelevant; ranking comes from Firestore preferences.
COURSE_SCHEDULE_IDS = {
    "Edgewood": None,
    "Rose Creek": None,
    "Osgood": None,
    "El Zagal": None,
    "Prairiewood": None,
}

# TODO(discovery §2.1): booking_class from the captured times request.
FOREUP_BOOKING_CLASS = os.getenv("FOREUP_BOOKING_CLASS", "")

# Pro shop phone numbers, used by the §4.4 fail-safe so Byron can cancel by
# phone if the API cancel fails. TODO Byron: verify numbers.
PRO_SHOP_PHONES = {
    "Edgewood": "(701) 232-2824",
    "Rose Creek": "(701) 235-5100",
    "Osgood": "(701) 277-9991",
    "El Zagal": "(701) 232-8156",
    "Prairiewood": "(701) 282-6825",
}

# Defaults for the Firestore preferences doc. Created on first run if missing.
DEFAULT_PREFERENCES = {
    # Safety: dry_run logs the slot it *would* book instead of booking (§ Phase 2).
    # Flip to False in Firestore only after a few clean release windows.
    "dry_run": True,
    # TODO Byron (§3.3): rank the courses you actually want.
    "courses_priority": ["Edgewood", "Rose Creek", "Osgood"],
    "days": ["Sat", "Sun"],
    "time_window": ["07:00", "10:30"],
    "ideal_time": "08:00",
    "players": 2,
    "holes": 18,
    "max_bookings_per_week": 2,
    # Watchdog thresholds (§4.2). TODO Byron: tune.
    "weather": {
        "precip_probability_max": 60,   # percent
        "wind_mph_max": 25,
        "temp_f_min": 45,
    },
    # Calendar conflict window around the tee time (§4.2).
    "travel_buffer_minutes": 45,
    "round_duration_hours": 4.5,
    # Ask-first cancel flow (§4.3).
    "ask_first_cutoff_hours": 4,    # inside this, cancel immediately
    "auto_cancel_at_hours": 3,      # no reply by T-3h -> cancel
    # §0 blocker: exact release clock time, local. TODO Byron: confirm
    # (the Scheduler job must be created to fire ~60s before this).
    "release_time_local": "06:00",
    "release_days_ahead": 3,
}


def load_secret(secret_name: str, project_id: str | None = None) -> str | None:
    """Load a secret: env var first, then GCP Secret Manager."""
    env_value = os.getenv(secret_name.upper().replace("-", "_"))
    if env_value:
        return env_value
    try:
        from google.cloud import secretmanager
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id or GCP_PROJECT}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        logger.info("Loaded %s from Secret Manager", secret_name)
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.warning("Could not load secret %s: %s", secret_name, e)
        return None
