"""Slot scoring (§3.3): course rank weight + proximity to ideal time.

Higher score wins. Slots outside the time window or for unranked courses
score None and are dropped.
"""

from datetime import datetime

# A one-step-better course outranks ~30 minutes of time proximity. Tune via
# preferences once Byron decides "specific course vs earlier time" (§3.3).
COURSE_RANK_WEIGHT = 60.0
MINUTES_PENALTY = 1.0


def score(slot_time: datetime, course: str, prefs: dict) -> float | None:
    window_start, window_end = prefs["time_window"]
    hhmm = slot_time.strftime("%H:%M")
    if not (window_start <= hhmm <= window_end):
        return None
    try:
        rank = prefs["courses_priority"].index(course)
    except ValueError:
        return None

    ideal_h, ideal_m = map(int, prefs["ideal_time"].split(":"))
    minutes_off = abs((slot_time.hour * 60 + slot_time.minute) - (ideal_h * 60 + ideal_m))

    top_rank_bonus = (len(prefs["courses_priority"]) - rank) * COURSE_RANK_WEIGHT
    return top_rank_bonus - minutes_off * MINUTES_PENALTY


def best(slots: list[dict], prefs: dict) -> dict | None:
    """slots: [{'time': datetime, 'course': str, 'raw': <foreup slot>}]"""
    scored = [
        (s_val, slot)
        for slot in slots
        if (s_val := score(slot["time"], slot["course"], prefs)) is not None
    ]
    if not scored:
        return None
    return max(scored, key=lambda pair: pair[0])[1]
