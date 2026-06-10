"""Notifications (§5): Twilio SMS primary, email fallback, log-only last resort.

Every message includes course, date/time, and a one-tap action link. Failures
to notify are themselves audited — but never raise, because notification
failure must not break a cancel in progress.
"""

import logging
import os

import config
import store

logger = logging.getLogger(__name__)

BYRON_PHONE = os.getenv("TEE_AGENT_PHONE", "")        # TODO Byron: +1701...
BYRON_EMAIL = os.getenv("TEE_AGENT_EMAIL", "blsnider@scheels.com")
BASE_URL = os.getenv("TEE_AGENT_BASE_URL", "")        # Cloud Run URL, set at deploy


def action_link(reservation_id: str, action: str) -> str:
    return f"{BASE_URL}/confirm/{reservation_id}?action={action}"


def send(message: str, critical: bool = False) -> None:
    """SMS Byron; on failure fall back to email; critical failures also page
    via both channels. Never raises."""
    sent = _sms(message)
    if not sent or critical:
        _email("Tee-agent alert" + (" (CRITICAL)" if critical else ""), message)
    if not sent:
        logger.error("NOTIFICATION FALLBACK USED: %s", message)
        store.audit("notify.sms_failed", {"message": message})


def _sms(message: str) -> bool:
    sid = config.load_secret("twilio-account-sid")
    token = config.load_secret("twilio-auth-token")
    from_number = config.load_secret("twilio-from-number")
    if not (sid and token and from_number and BYRON_PHONE):
        logger.warning("Twilio not configured; SMS skipped")
        return False
    try:
        from twilio.rest import Client
        Client(sid, token).messages.create(
            to=BYRON_PHONE, from_=from_number, body=message[:1500]
        )
        return True
    except Exception as e:
        logger.error("Twilio send failed: %s", e)
        return False


def _email(subject: str, body: str) -> bool:
    """SendGrid email (zero-cost alternative path, §5)."""
    key = config.load_secret("sendgrid-api-key")
    if not key:
        logger.warning("SendGrid not configured; email skipped")
        return False
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail
        sendgrid.SendGridAPIClient(key).send(Mail(
            from_email=BYRON_EMAIL, to_emails=BYRON_EMAIL,
            subject=subject, plain_text_content=body,
        ))
        return True
    except Exception as e:
        logger.error("SendGrid send failed: %s", e)
        return False


def page_cancel_failure(booking: dict) -> None:
    """§4.4 fail-safe: API cancel failed — Byron must phone the pro shop
    before the 2-hour deadline."""
    course = booking.get("course", "?")
    phone = config.PRO_SHOP_PHONES.get(course, "see foreupsoftware.com")
    send(
        f"🚨 CANCEL FAILED: {course} {booking.get('tee_time_display', '?')}. "
        f"API cancel did not go through. CALL THE PRO SHOP NOW to cancel "
        f"before the 2-hour deadline: {phone}",
        critical=True,
    )
