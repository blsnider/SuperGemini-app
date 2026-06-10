"""§2.1 discovery, automated: probe fargogolf.net + ForeUp from Cloud Run
(which has open egress) and report everything needed to configure the client.

One-shot diagnostic — invoked via /discover, results logged + returned as
JSON. Safe to run repeatedly; it only does GETs plus one login POST.
"""

import logging
import re

import requests

import config

logger = logging.getLogger(__name__)

UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}

FARGO_PAGES = [
    "https://www.fargogolf.net/",
    "https://www.fargogolf.net/tee-times/",
    "https://www.fargogolf.net/tee-times",
    "https://fargogolf.net/",
]

BOOKING_LINK_RE = re.compile(
    r"https?://(?:app\.)?foreupsoftware\.com/index\.php/booking/(\d+)(?:/(\d+))?")

# JS globals on ForeUp booking pages that describe schedules/booking classes.
INTERESTING_VARS = re.compile(
    r"(?:var|let|const)\s+([A-Za-z_]*(?:SCHEDULE|BOOKING|COURSE|CLASS)[A-Za-z_]*)\s*=\s*(.{0,2000}?);\s*\n",
    re.IGNORECASE | re.DOTALL)


def run(date_str: str) -> dict:
    out = {"fargo_pages": [], "booking_links": [], "courses": {},
           "times_probe": {}, "login_probe": {}}
    s = requests.Session()
    s.headers.update(UA)

    found: dict[str, str | None] = {}
    for url in FARGO_PAGES:
        try:
            r = s.get(url, timeout=15)
            out["fargo_pages"].append({"url": url, "status": r.status_code, "bytes": len(r.text)})
            for cid, sched in BOOKING_LINK_RE.findall(r.text):
                found.setdefault(cid, sched or None)
        except Exception as e:
            out["fargo_pages"].append({"url": url, "error": str(e)})
    out["booking_links"] = [{"course_id": c, "schedule_id": sc} for c, sc in found.items()]

    # Fargo's live portal is an aggregate ForeUp page listing all 5 courses
    # (link found in course 19984's booking_rules). Its embedded JSON carries
    # every course_id/schedule_id pair.
    out["aggregate"] = {}
    try:
        r = s.get("https://foreupsoftware.com/index.php/booking/a/19956/18", timeout=15)
        out["aggregate"]["status"] = r.status_code
        out["aggregate"]["course_ids"] = sorted(set(re.findall(r'"course_id"\s*:\s*"?(\d+)', r.text)))
        out["aggregate"]["schedule_ids"] = sorted(set(re.findall(r'"(?:schedule_id|teesheet_id)"\s*:\s*"?(\d+)', r.text)))
        out["aggregate"]["booking_class_ids"] = sorted(set(re.findall(r'"booking_class_id"\s*:\s*"?(\d+)', r.text)))
        names = re.findall(r'"(?:name|title|teesheet_title|course_name|schedule_name)"\s*:\s*"([^"]{3,60})"', r.text)
        out["aggregate"]["names_sample"] = sorted(set(names))[:25]
        for cid in out["aggregate"]["course_ids"]:
            found.setdefault(cid, None)
    except Exception as e:
        out["aggregate"]["error"] = str(e)

    schedule_ids = []
    for course_id, sched in found.items():
        url = f"https://foreupsoftware.com/index.php/booking/{course_id}" + (f"/{sched}" if sched else "")
        info: dict = {"url": url}
        try:
            page = s.get(url, timeout=15)
            info["status"] = page.status_code
            title = re.search(r"<title>(.*?)</title>", page.text, re.DOTALL)
            info["title"] = title.group(1).strip()[:120] if title else None
            info["vars"] = {name: val.strip()[:1500] for name, val in INTERESTING_VARS.findall(page.text)}
            info["has_captcha"] = bool(re.search(r"recaptcha|hcaptcha|turnstile", page.text, re.I))
            for sid in re.findall(r'"schedule_id"\s*:\s*"?(\d+)"?', page.text):
                if sid not in schedule_ids:
                    schedule_ids.append(sid)
            if sched and sched not in schedule_ids:
                schedule_ids.append(sched)
        except Exception as e:
            info["error"] = str(e)
        out["courses"][course_id] = info

    # Unauthenticated times probe — public booking classes often allow this.
    for sid in schedule_ids[:8]:
        try:
            r = s.get(
                "https://foreupsoftware.com/index.php/api/booking/times",
                params={"time": "all", "date": date_str, "holes": "all",
                        "players": 0, "schedule_id": sid, "specials_only": 0,
                        "api_key": "no_limits"},
                timeout=15)
            body = r.text[:800]
            out["times_probe"][sid] = {
                "status": r.status_code,
                "is_json_array": body.lstrip().startswith("["),
                "sample": body,
            }
        except Exception as e:
            out["times_probe"][sid] = {"error": str(e)}

    # Login probe with stored credentials.
    jwt = None
    username = config.load_secret("foreup-username")
    password = config.load_secret("foreup-password")
    if username and password:
        course_id = next(iter(found), "")
        try:
            r = s.post(
                "https://foreupsoftware.com/index.php/api/booking/users/login",
                data={"username": username, "password": password,
                      "course_id": course_id, "api_key": "no_limits",
                      "booking_class_id": ""},
                timeout=15)
            data = r.json() if r.status_code == 200 else {}
            jwt = data.get("jwt")
            out["login_probe"] = {
                "status": r.status_code,
                "jwt_in_body": bool(jwt),
                "person_id": data.get("person_id"),
                "home_course_id": data.get("course_id"),
                "booking_class_id_on_account": data.get("booking_class_id"),
            }
        except Exception as e:
            out["login_probe"] = {"error": str(e)}
    else:
        out["login_probe"] = {"error": "credentials not in Secret Manager"}

    # Course config: lists every schedule (course) + booking class for the org.
    course_ids = set(found) | {out.get("login_probe", {}).get("home_course_id") or ""} - {""}
    out["course_config"] = {}
    for cid in sorted(c for c in course_ids if c):
        try:
            r = s.get(f"https://foreupsoftware.com/index.php/api/booking/courses/{cid}",
                      timeout=15)
            info = {"status": r.status_code}
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else [data]
                info["schedules"] = [
                    {"schedule_id": sch.get("teesheet_id") or sch.get("schedule_id") or sch.get("id"),
                     "name": sch.get("teesheet_title") or sch.get("title") or sch.get("name")}
                    for item in items for sch in (item.get("schedules") or [])
                ]
                info["booking_classes"] = [
                    {"booking_class_id": bc.get("booking_class_id") or bc.get("id"),
                     "name": bc.get("name") or bc.get("title")}
                    for item in items for bc in (item.get("bookingClasses") or item.get("booking_classes") or [])
                ]
                if not info["schedules"] and not info["booking_classes"]:
                    info["raw_sample"] = r.text[:3000]
            else:
                info["raw_sample"] = r.text[:300]
            out["course_config"][cid] = info
        except Exception as e:
            out["course_config"][cid] = {"error": str(e)}

    # Authenticated times probe across every discovered schedule.
    all_sids = {str(sch["schedule_id"]) for cfg in out["course_config"].values()
                for sch in cfg.get("schedules", []) if sch.get("schedule_id")} | set(schedule_ids)
    all_bcs = [str(bc["booking_class_id"]) for cfg in out["course_config"].values()
               for bc in cfg.get("booking_classes", []) if bc.get("booking_class_id")][:3]
    headers = {"X-Authorization": f"Bearer {jwt}", "Api-Key": "no_limits"} if jwt else {}
    out["times_probe_auth"] = {}
    for sid in sorted(all_sids)[:10]:
        for bc in (all_bcs or [""]):
            try:
                r = s.get(
                    "https://foreupsoftware.com/index.php/api/booking/times",
                    params={"time": "all", "date": date_str, "holes": "all",
                            "players": 0, "schedule_id": sid, "booking_class": bc,
                            "specials_only": 0, "api_key": "no_limits"},
                    headers=headers, timeout=15)
                ok = r.text.lstrip().startswith("[") and len(r.text) > 5
                out["times_probe_auth"][f"sched={sid} bc={bc}"] = {
                    "status": r.status_code, "got_slots": ok,
                    "sample": r.text[:400] if ok else r.text[:80],
                }
                if ok:
                    break  # found a working combo for this schedule
            except Exception as e:
                out["times_probe_auth"][f"sched={sid} bc={bc}"] = {"error": str(e)}

    return out


def booking_test(date_str: str) -> dict:
    """§2.3 verification: book ONE throwaway slot (last of the day, El Zagal)
    and cancel it immediately. Captures every raw payload/response so
    foreup.py can be corrected against reality. Cancel runs in `finally` —
    a leftover reservation is reported loudly, never silent.
    """
    out = {"date": date_str, "steps": []}
    s = requests.Session()
    s.headers.update(UA)

    def step(name, resp):
        rec = {"step": name, "status": resp.status_code, "body": resp.text[:1200]}
        out["steps"].append(rec)
        return rec

    r = s.post(config.FOREUP_LOGIN_URL, data={
        "username": config.load_secret("foreup-username"),
        "password": config.load_secret("foreup-password"),
        "course_id": config.FOREUP_LOGIN_COURSE_ID,
        "booking_class_id": config.FOREUP_BOOKING_CLASS,
        "api_key": "no_limits"}, timeout=15)
    jwt = r.json().get("jwt") if r.status_code == 200 else None
    out["steps"].append({"step": "login", "status": r.status_code, "jwt": bool(jwt)})
    if not jwt:
        return out
    s.headers.update({"X-Authorization": f"Bearer {jwt}", "Api-Key": "no_limits"})

    r = s.get(f"{config.FOREUP_BASE_URL}/times", params={
        "time": "all", "date": date_str, "holes": "all", "players": 0,
        "schedule_id": config.COURSE_SCHEDULE_IDS["El Zagal"],
        "booking_class": config.FOREUP_BOOKING_CLASS,
        "specials_only": 0, "api_key": "no_limits"}, timeout=15)
    slots = r.json() if r.text.lstrip().startswith("[") else []
    out["steps"].append({"step": "times", "status": r.status_code, "n_slots": len(slots)})
    if not slots:
        return out
    slot = slots[-1]  # least desirable: last tee time of the day
    out["chosen_slot"] = {k: slot.get(k) for k in
                          ("time", "schedule_id", "course_id", "teesheet_side_id",
                           "holes", "green_fee", "require_credit_card", "booking_class_id")}

    ttid = None
    try:
        pend_payload = {
            "time": slot["time"], "holes": slot.get("holes", 9), "players": 1,
            "carts": False, "schedule_id": slot["schedule_id"],
            "teesheet_side_id": slot.get("teesheet_side_id"),
            "course_id": slot.get("course_id"),
            "booking_class_id": config.FOREUP_BOOKING_CLASS, "duration": 1,
            "foreup_discount": False, "foreup_trade_discount_rate": 0,
            "trade_min_players": 0, "cart_fee": 0, "cart_fee_tax": 0,
            "green_fee": slot.get("green_fee", 0), "green_fee_tax": 0,
        }
        r = s.post(f"{config.FOREUP_BASE_URL}/pending_reservation",
                   json=pend_payload, timeout=15)
        rec = step("pending_reservation(json)", r)
        pend = {}
        try:
            pend = r.json()
        except Exception:
            pass
        if not pend.get("success"):
            r = s.post(f"{config.FOREUP_BASE_URL}/pending_reservation",
                       data=pend_payload, timeout=15)
            rec = step("pending_reservation(form)", r)
            try:
                pend = r.json()
            except Exception:
                pend = {}
        pending_id = pend.get("reservation_id") or pend.get("id")
        out["pending_id"] = pending_id
        if not pending_id:
            return out

        commit = dict(slot)
        commit.update({"pending_reservation_id": pending_id, "players": 1,
                       "carts": False, "promo_code": "", "customer_message": "",
                       "notes": "", "duration": 1})
        r = s.post(f"{config.FOREUP_BASE_URL}/users/reservations",
                   json=commit, timeout=15)
        step("commit_reservation", r)
        try:
            booked = r.json()
            ttid = booked.get("TTID") or booked.get("teetime_id") or booked.get("reservation_id")
        except Exception:
            ttid = None
        out["ttid"] = ttid
    finally:
        if ttid:
            for attempt in range(3):
                r = s.delete(f"{config.FOREUP_BASE_URL}/users/reservations/{ttid}",
                             timeout=15)
                step(f"cancel_attempt_{attempt + 1}", r)
                if r.status_code in (200, 204):
                    out["canceled"] = True
                    break
            else:
                out["canceled"] = False
                out["ALERT"] = ("RESERVATION STILL ACTIVE — cancel manually NOW: "
                                f"El Zagal {slot.get('time')} (pro shop "
                                f"{config.PRO_SHOP_PHONES['El Zagal']})")
        elif out.get("pending_id"):
            out["note"] = "Hold created but never committed; ForeUp expires pending holds on their own."
    return out
