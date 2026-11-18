"""3B.3  Fake data generator: 11 fields per record, saved to SQLite, exportable as CSV or JSON."""
import csv
import io
import json
import re
import uuid
from datetime import date

from faker import Faker
from flask import Blueprint, Response, jsonify, request

from database import get_db
from helpers import api_error, current_user_id, json_body, login_required

bp = Blueprint("fake_data", __name__)

LOCALES = {"en_PH": "Philippines", "en_US": "United States"}
FIELDS = ["first_name", "last_name", "sex", "birthdate", "age", "address",
          "city", "mobile_number", "email", "job", "company"]
MAX_RECORDS = 500
LIST_LIMIT = 100                        # rows shown on screen; exports include everything

PH_MOBILE_PREFIXES = ["905", "906", "915", "917", "926", "927", "935", "945", "956", "977", "995", "999"]
NANP_FIRST_DIGIT = ("2", "3", "4", "5", "6", "7", "8", "9")

_fakers = {}                            # one Faker object per locale, created on first use


# --------------------------------------------------------------------------
# Building records
# --------------------------------------------------------------------------
def get_faker(locale):
    if locale not in _fakers:
        _fakers[locale] = Faker(locale)
    return _fakers[locale]


def make_mobile(fk, locale):
    """Faker's phone_number() mixes landlines, extensions and odd formats, which the SMS
    dispatcher would reject. These fixed patterns always give a valid mobile number."""
    if locale == "en_PH":
        return f"+63 {fk.random_element(PH_MOBILE_PREFIXES)} {fk.numerify('###')} {fk.numerify('####')}"
    # US numbers: area code and exchange cannot start with 0 or 1.
    return (f"+1 {fk.random_element(NANP_FIRST_DIGIT)}{fk.numerify('##')}-"
            f"{fk.random_element(NANP_FIRST_DIGIT)}{fk.numerify('##')}-{fk.numerify('####')}")


def calculate_age(born):
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def make_record(fk, locale):
    """One fake person with all 11 fields."""
    sex = fk.random_element(("Male", "Female"))
    first_name = fk.first_name_male() if sex == "Male" else fk.first_name_female()
    born = fk.date_of_birth(minimum_age=18, maximum_age=70)
    return {
        "first_name": first_name,
        "last_name": fk.last_name(),
        "sex": sex,
        "birthdate": born.isoformat(),
        "age": calculate_age(born),
        "address": fk.address().replace("\n", ", "),
        "city": fk.city(),
        "mobile_number": make_mobile(fk, locale),
        "email": fk.email(),
        "job": fk.job(),
        "company": fk.company(),
    }


def _save_records(db, user_id, batch_id, records):
    db.executemany(
        f"INSERT INTO fake_records (user_id, batch_id, {', '.join(FIELDS)}) "
        f"VALUES (?, ?, {', '.join('?' * len(FIELDS))})",
        [(user_id, batch_id, *(rec[f] for f in FIELDS)) for rec in records])
    db.commit()


# --------------------------------------------------------------------------
# Exporting
# --------------------------------------------------------------------------
def csv_safe(value):
    """Stop spreadsheet formula injection when the CSV is opened in Excel."""
    text = str(value)
    if re.fullmatch(r"\+\d[\d ]*", text):       # a plain phone number such as +63 917 123 4567
        return text
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _as_csv(rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(FIELDS)
    for row in rows:
        writer.writerow([csv_safe(row[f]) for f in FIELDS])
    return buffer.getvalue()


def _as_json(rows):
    return json.dumps([dict(row) for row in rows], indent=2)


EXPORT_FORMATS = {
    "csv": (_as_csv, "text/csv"),
    "json": (_as_json, "application/json"),
}


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@bp.post("/api/fake-data/generate")
@login_required
def generate_fake_data():
    data = json_body()
    try:
        count = int(data.get("count", 10))
    except (TypeError, ValueError):
        return api_error("count must be a whole number", 400)
    if not 1 <= count <= MAX_RECORDS:
        return api_error(f"count must be between 1 and {MAX_RECORDS}", 400)
    locale = data.get("locale", "en_PH")
    if locale not in LOCALES:
        return api_error("Unsupported locale", 400)

    fk = get_faker(locale)
    records = [make_record(fk, locale) for _ in range(count)]
    batch_id = uuid.uuid4().hex[:8]
    _save_records(get_db(), current_user_id(), batch_id, records)

    return jsonify(batch_id=batch_id, count=count, locale=locale,
                   fields=FIELDS, records=records), 201


@bp.get("/api/fake-data")
@login_required
def list_fake_data():
    db, user_id = get_db(), current_user_id()
    total = db.execute("SELECT COUNT(*) FROM fake_records WHERE user_id = ?",
                       (user_id,)).fetchone()[0]
    rows = db.execute(
        f"SELECT id, batch_id, {', '.join(FIELDS)} FROM fake_records "
        f"WHERE user_id = ? ORDER BY id DESC LIMIT {LIST_LIMIT}", (user_id,)).fetchall()
    return jsonify(total=total, fields=FIELDS, records=[dict(r) for r in rows])


@bp.delete("/api/fake-data")
@login_required
def clear_fake_data():
    db = get_db()
    cur = db.execute("DELETE FROM fake_records WHERE user_id = ?", (current_user_id(),))
    db.commit()
    return jsonify(success=True, deleted=cur.rowcount)


@bp.get("/api/fake-data/export")
@login_required
def export_fake_data():
    fmt = request.args.get("format", "csv")
    if fmt not in EXPORT_FORMATS:
        return api_error("format must be csv or json", 400)

    rows = get_db().execute(
        f"SELECT {', '.join(FIELDS)} FROM fake_records WHERE user_id = ? ORDER BY id",
        (current_user_id(),)).fetchall()
    render, mimetype = EXPORT_FORMATS[fmt]
    return Response(render(rows), mimetype=mimetype,
                    headers={"Content-Disposition": f"attachment; filename=fake_records.{fmt}"})
