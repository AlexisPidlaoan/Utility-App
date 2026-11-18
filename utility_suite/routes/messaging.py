"""3B.2  SMS & messaging dispatcher (simulated: no real SMS is sent)."""
import math
import random
import re

from flask import Blueprint, jsonify, request

from database import get_db
from helpers import api_error, current_user_id, json_body, login_required

bp = Blueprint("messaging", __name__)

MAX_MESSAGE_LEN = 640
STATUSES = ("queued", "sent", "delivered", "failed")
BULK_LIMIT = 50                         # most recent stored contacts used by a bulk send
FAILURE_RATE = 0.10                     # share of messages the simulated carrier fails


# --------------------------------------------------------------------------
# Phone numbers and message text
# --------------------------------------------------------------------------
def normalize_number(raw):
    """Return the number in +E.164 form, or None if it is not a plausible mobile number."""
    s = re.sub(r"[\s\-().]", "", str(raw or ""))
    if re.fullmatch(r"09\d{9}", s):             # Philippine local format
        return "+63" + s[1:]
    if re.fullmatch(r"639\d{9}", s):
        return "+" + s
    if re.fullmatch(r"\+\d{8,15}", s):
        return s
    return None


def sms_segments(text):
    """One SMS holds 160 characters; longer messages are split into 153-character parts."""
    return 1 if len(text) <= 160 else math.ceil(len(text) / 153)


def validate_message(text):
    """Return an error message, or None if the text is acceptable."""
    if not text:
        return "Message cannot be empty"
    if len(text) > MAX_MESSAGE_LEN:
        return f"Message is limited to {MAX_MESSAGE_LEN} characters"
    return None


def personalize(template, contact):
    """Fill in {first_name}, {last_name} and {name}.

    Plain replace (not str.format), so user text can never break or probe the template.
    """
    first, last = contact["first_name"], contact["last_name"]
    return (template.replace("{first_name}", first)
                    .replace("{last_name}", last)
                    .replace("{name}", f"{first} {last}"))


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------
def simulate_carrier(number):
    """Stand-in for a real provider (e.g. Twilio). Replace this function to go live."""
    if number.endswith("0000"):
        return "failed", "Simulated carrier rejection"
    if random.random() < FAILURE_RATE:
        return "failed", "Simulated network timeout"
    return "delivered", None


def dispatch_message(db, user_id, number, body):
    """queued -> sent -> delivered/failed, with a timestamp stored at each stage."""
    cur = db.execute(
        "INSERT INTO message_logs (user_id, recipient, message_body, segments, status) "
        "VALUES (?, ?, ?, ?, 'queued')", (user_id, number, body, sms_segments(body)))
    message_id = cur.lastrowid

    db.execute("UPDATE message_logs SET status = 'sent', sent_at = CURRENT_TIMESTAMP WHERE id = ?",
               (message_id,))
    status, reason = simulate_carrier(number)
    db.execute("UPDATE message_logs SET status = ?, failure_reason = ?, "
               "finished_at = CURRENT_TIMESTAMP WHERE id = ?", (status, reason, message_id))
    return status, reason


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@bp.post("/api/messages/send")
@login_required
def send_message():
    data = json_body()
    number = normalize_number(data.get("recipient"))
    body = str(data.get("message") or "").strip()

    if not number:
        return api_error("Enter a valid mobile number (e.g. 09171234567 or +639171234567)", 400)
    problem = validate_message(body)
    if problem:
        return api_error(problem, 400)

    db = get_db()
    status, reason = dispatch_message(db, current_user_id(), number, body)
    db.commit()
    return jsonify(success=True, recipient=number, status=status, failure_reason=reason,
                   segments=sms_segments(body)), 201


@bp.post("/api/messages/bulk")
@login_required
def bulk_send():
    """Send a template to the mobile numbers of the stored fake records."""
    template = str(json_body().get("message") or "").strip()
    problem = validate_message(template)
    if problem:
        return api_error(problem, 400)

    db, user_id = get_db(), current_user_id()
    contacts = db.execute(
        "SELECT first_name, last_name, mobile_number FROM fake_records "
        f"WHERE user_id = ? ORDER BY id DESC LIMIT {BULK_LIMIT}", (user_id,)).fetchall()
    if not contacts:
        return api_error("No stored fake records yet. Generate some first.", 400)

    summary = {"attempted": 0, "delivered": 0, "failed": 0, "skipped": 0}
    for contact in contacts:
        number = normalize_number(contact["mobile_number"])
        if not number:
            summary["skipped"] += 1
            continue
        body = personalize(template, contact)[:MAX_MESSAGE_LEN]
        status, _reason = dispatch_message(db, user_id, number, body)
        summary["attempted"] += 1
        summary[status] += 1
    db.commit()
    return jsonify(success=True, **summary), 201


@bp.get("/api/messages")
@login_required
def list_messages():
    status = request.args.get("status", "")
    if status and status not in STATUSES:
        return api_error("Invalid status filter", 400)

    query = ("SELECT id, recipient, message_body, segments, status, failure_reason, "
             "queued_at, sent_at, finished_at FROM message_logs WHERE user_id = ?")
    params = [current_user_id()]
    if status:
        query += " AND status = ?"
        params.append(status)

    rows = get_db().execute(query + " ORDER BY id DESC LIMIT 100", params).fetchall()
    return jsonify(messages=[dict(r) for r in rows])
