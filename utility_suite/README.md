# Developer & Admin Utility Suite

Mini capstone, **Category 3B: Utilities**. A Flask + SQLite web app with a login system and three tools:
a URL shortener, a fake data generator, and an SMS & messaging dispatcher.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows      (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000>, click **Create one** to register, and you are in. The database
(`utility_suite.db`) and a session key (`.secret_key`) are created automatically on first run.

> If you ran the earlier starter version first, its old `utility_suite.db` is not compatible. The app
> detects this, renames it to `utility_suite.db.legacy-<timestamp>` (nothing is deleted) and starts fresh.

## Requirement checklist

| Requirement | Where it is done |
|---|---|
| Passwords hashed and salted with `hashlib`, never stored in plain text | `security.py` (`hash_password()` / `verify_password()`): PBKDF2-HMAC-SHA256, 200,000 rounds, random 16-byte salt per user, stored as `pbkdf2_sha256$rounds$salt$hash` |
| GUI with username and password fields | `templates/login.html` (login and registration) |
| On login, look the username up in the database and verify the password against the stored hash | `routes/auth.py`, `POST /api/login`: queries `users`, recomputes the hash with the stored salt, compares with `hmac.compare_digest` |
| 3B.1 URL shortening | URL Shortener tab: Base62 or random codes, custom aliases, redirect, click tracking |
| 3B.2 SMS | SMS & Messaging tab: simulated dispatch, status lifecycle, templates, bulk send, filterable log |
| 3B.3 Fake data: 10 fields, at least 10 records, stored | Fake Data tab: the user **chooses any of 16 fields** (1 to 16 columns), default **10 records** per run (1 to 500), saved in the `fake_records` table |

## What each tool does

**URL Shortener**
- *Base62 (from ID)* converts the database row ID to Base62 (`0-9a-zA-Z`), so codes are unique by construction.
  *Random* uses `secrets` and retries on the rare collision (the `UNIQUE` constraint is the safety net).
- Only `http://` and `https://` links are accepted (blocks `javascript:`, `data:` and `file:` links).
- Each visit to `/<code>` redirects (HTTP 302), adds 1 to `clicks`, and logs time, referrer and browser in `url_clicks`.
- The **Stats** button shows clicks per day and the 10 most recent clicks.

**Fake Data Generator**
- **Choose your fields.** Tick any of **16 fields** (1 to 16 columns): first name, last name, full name, sex, birthdate, age,
  civil status, address, city, ZIP code, country, mobile number, email, username, job, company.
  For example one user can pick only name, birthdate and address, and another only age and last name.
  Only the ticked fields are generated and saved (the others stay empty in the database), and the table and the
  CSV/JSON exports show only the columns that hold data. Related fields stay consistent (age matches birthdate,
  full name matches first + last name).
- In the API, send `"fields": ["first_name", "birthdate", "address"]` to `POST /api/fake-data/generate` (leave it out for all 16).
  `GET /api/fake-data/fields` lists the choices.
- Locale: Philippines (`en_PH`) or United States (`en_US`). Mobile numbers always use valid patterns
  (`+63 9XX XXX XXXX` / `+1 XXX-XXX-XXXX`) so they can be used for messaging.
- Every generated record is saved to SQLite. You can download all of them as CSV or JSON, or clear them.

**SMS & Messaging Dispatcher** (simulated; no real SMS is sent)
- Numbers are normalised to `+E.164` (`0917 123 4567` becomes `+639171234567`).
- Each message goes `queued → sent → delivered / failed`, with a timestamp at every stage and a failure reason.
  The carrier is simulated by `simulate_carrier()` in `routes/messaging.py`: numbers ending in `0000` always fail, about 10% of others fail.
  Replace that one function with a real provider call (e.g. Twilio) to go live.
- **Bulk send** sends a template (`{first_name}`, `{last_name}`, `{name}`) to your stored fake contacts.
  Only records that include the **Mobile number** field can be messaged; a name placeholder is left blank if that field was not generated.
- The message log can be filtered by status. Segments are counted (160 characters, then 153 per part).

## Security notes
- Passwords: salted PBKDF2, constant-time comparison, same error for unknown user and wrong password.
- Every query is parameterised (`?` placeholders), so SQL injection is not possible.
- The browser UI builds all tables with `textContent`, never `innerHTML`, so stored text cannot run as script.
- Data is per user: you can only see, export, or delete your own links, records and messages.
- Session cookie is `HttpOnly` and `SameSite=Lax`; the API only accepts JSON bodies.
- Set `SECRET_KEY` as an environment variable in production. Do not commit `.secret_key` or the `.db` file (both are in `.gitignore`).

## Tests

```bash
python -m unittest discover -s tests -v
```

29 tests cover hashing and salting, login/logout, access control, URL validation, redirects and click logging,
the 10-records storage rule, choosing 1 to 16 fields (different fields per user, invalid choices, upgrading an old database), CSV/JSON export, SMS lifecycle, bulk send, and data isolation between users.
They use a temporary database, so your real data is never touched.

## Project layout

Each file does one job, and each tool has its own file under `routes/`:

```
app.py                  entry point: builds the Flask app and starts it (about 20 lines)
config.py               settings and the session secret key
database.py             SQLite connection and first-run setup
security.py             password hashing with hashlib
helpers.py              login_required and small JSON helpers shared by all routes
schema.sql              SQLite schema (users, urls, url_clicks, fake_records, message_logs)
routes/
    auth.py             register, login, logout
    pages.py            login page, dashboard page, summary numbers
    shortener.py        3B.1  URL shortener and click tracking
    messaging.py        3B.2  SMS dispatcher
    fake_data.py        3B.3  fake data generator and CSV/JSON export
templates/              login.html, index.html (tabbed dashboard)
static/                 style.css, app.js
tests/test_app.py       automated tests
requirements.txt        flask, faker
```

Inside each route file the order is the same: constants, small helper functions, then the routes.

## Demo script (about 5 minutes)

1. **Register** a new account, then show `users` in the database: the password column holds salt + hash only.
2. **Log out and log in** with a wrong password (error), then the right one.
3. **URL Shortener:** shorten a long link, then one with a custom alias. Open both short links in new tabs.
   Click **Stats** to show the click count and referrer.
4. **Fake Data:** tick only **First name, Birthdate, Address** and generate 10 records (Philippines): the table shows just
   those 3 columns. Click **Clear all**, tick only **Age** and **Last name**, generate again, and show the different columns.
   Then **Select all** to show all 16. **Download CSV** (only the chosen columns). Refresh to show the records are still
   there (stored in SQLite).
5. **SMS:** send one message to `0917 123 4567`. Then **Bulk send** to the stored contacts and filter the log by
   `failed` to show failure reasons. Send to `09170000000` to show a forced failure.
6. Mention the safeguards: parameterised SQL, URL scheme check, per-user data, `textContent` rendering.

## Ideas to extend
- Email channel next to SMS (e.g. `smtplib` with a local debug server, or a real provider)
- Link expiry dates and a chart of clicks over time
- Login rate-limiting and a change-password page
