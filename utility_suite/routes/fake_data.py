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

# Every field a user can pick, in display order: key -> label.
FIELD_LABELS = {
    "first_name": "First name",
    "last_name": "Last name",
    "full_name": "Full name",
    "sex": "Sex",
    "birthdate": "Birthdate",
    "age": "Age",
    "civil_status": "Civil status",
    "address": "Address",
    "city": "City",
    "zip_code": "ZIP code",
    "country": "Country",
    "mobile_number": "Mobile number",
    "email": "Email",
    "username": "Username",
    "job": "Job",
    "company": "Company",
}
FIELDS = list(FIELD_LABELS)
MAX_FIELDS = len(FIELDS)                # 16: a record can have at most this many columns
CIVIL_STATUSES = ("Single", "Married", "Widowed", "Separated")

MAX_RECORDS = 500
LIST_LIMIT = 100                        # rows shown on screen; exports include everything

PH_MOBILE_PREFIXES = ["905", "906", "915", "917", "926", "927", "935", "945", "956", "977", "995", "999"]
NANP_FIRST_DIGIT = ("2", "3", "4", "5", "6", "7", "8", "9")

_fakers = {}                            # one Faker object per locale, created on first use


# --------------------------------------------------------------------------
# Choosing fields
# --------------------------------------------------------------------------
def parse_fields(raw):
    """Check the user's field choice. Returns (fields, error_message).

    - None (not sent) means every field.
    - Otherwise it must be a non-empty list of known field names. Duplicates are ignored and
      the result always comes back in the standard FIELDS order.
    The result is the only thing that is ever put into SQL column lists, so it is a whitelist.
    """
    if raw is None:
        return list(FIELDS), None
    if not isinstance(raw, list) or not all(isinstance(f, str) for f in raw):
        return None, "fields must be a list of field names"
    unknown = sorted(set(raw) - set(FIELDS))
    if unknown:
        return None, "Unknown field(s): " + ", ".join(unknown)
    if not raw:
        return None, f"Choose at least one field (up to {MAX_FIELDS})"
    chosen = set(raw)
    return [f for f in FIELDS if f in chosen], None


def used_fields(rows):
    """The fields that hold data in at least one row, in the standard order.

    Rows from different runs can have different fields, so tables and exports use this to show
    only the columns that are not empty.
    """
    return [f for f in FIELDS if any(row[f] is not None for row in rows)]


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


def make_record(fk, locale, fields=None):
    """One fake person, with only the requested fields (all 16 if `fields` is None).

    The whole person is built first so related fields agree (age matches birthdate, full name
    matches first and last name), then the requested fields are picked out.
    """
    sex = fk.random_element(("Male", "Female"))
    first_name = fk.first_name_male() if sex == "Male" else fk.first_name_female()
    last_name = fk.last_name()
    born = fk.date_of_birth(minimum_age=18, maximum_age=70)
    person = {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": f"{first_name} {last_name}",
        "sex": sex,
        "birthdate": born.isoformat(),
        "age": calculate_age(born),
        "civil_status": fk.random_element(CIVIL_STATUSES),
        "address": fk.address().replace("\n", ", "),
        "city": fk.city(),
        "zip_code": fk.postcode(),
        "country": LOCALES[locale],
        "mobile_number": make_mobile(fk, locale),
        "email": fk.email(),
        "username": fk.user_name(),
        "job": fk.job(),
        "company": fk.company(),
    }
    return {f: person[f] for f in (fields or FIELDS)}


def _save_records(db, user_id, batch_id, records, fields=None):
    """Insert the records. Only the chosen columns are written; the rest stay NULL."""
    fields = fields or FIELDS          # always from parse_fields() or FIELDS, never raw user text
    db.executemany(
        f"INSERT INTO fake_records (user_id, batch_id, {', '.join(fields)}) "
        f"VALUES (?, ?, {', '.join('?' * len(fields))})",
        [(user_id, batch_id, *(rec[f] for f in fields)) for rec in records])
    db.commit()


# --------------------------------------------------------------------------
# Exporting (only the columns that hold data)
# --------------------------------------------------------------------------
def csv_safe(value):
    """Stop spreadsheet formula injection when the CSV is opened in Excel."""
    text = str(value)
    if re.fullmatch(r"\+\d[\d ]*", text):       # a plain phone number such as +63 917 123 4567
        return text
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text


def _as_csv(rows):
    columns = used_fields(rows)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if row[f] is None else csv_safe(row[f]) for f in columns])
    return buffer.getvalue()


def _as_json(rows):
    columns = used_fields(rows)
    return json.dumps([{f: row[f] for f in columns} for row in rows], indent=2)


EXPORT_FORMATS = {
    "csv": (_as_csv, "text/csv"),
    "json": (_as_json, "application/json"),
}


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@bp.get("/api/fake-data/fields")
@login_required
def list_field_choices():
    """The fields a user can pick from, so the web page can draw its checkboxes."""
    return jsonify(max_fields=MAX_FIELDS,
                   fields=[{"key": key, "label": label} for key, label in FIELD_LABELS.items()])


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
    fields, problem = parse_fields(data.get("fields"))
    if problem:
        return api_error(problem, 400)

    fk = get_faker(locale)
    records = [make_record(fk, locale, fields) for _ in range(count)]
    batch_id = uuid.uuid4().hex[:8]
    _save_records(get_db(), current_user_id(), batch_id, records, fields)

    return jsonify(batch_id=batch_id, count=count, locale=locale,
                   fields=fields, records=records), 201


@bp.get("/api/fake-data")
@login_required
def list_fake_data():
    db, user_id = get_db(), current_user_id()
    total = db.execute("SELECT COUNT(*) FROM fake_records WHERE user_id = ?",
                       (user_id,)).fetchone()[0]
    rows = db.execute(
        f"SELECT id, batch_id, {', '.join(FIELDS)} FROM fake_records "
        f"WHERE user_id = ? ORDER BY id DESC LIMIT {LIST_LIMIT}", (user_id,)).fetchall()
    columns = used_fields(rows)
    records = [{"id": r["id"], "batch_id": r["batch_id"], **{f: r[f] for f in columns}} for r in rows]
    return jsonify(total=total, fields=columns, records=records)


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
