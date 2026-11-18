"""Automated tests for the Utility Suite.  Run from the project folder:

    python -m unittest discover -s tests -v

Uses a throw-away database file, so your real utility_suite.db is never touched.
"""
import csv
import io
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402  (after sys.path is set)
from database import init_db  # noqa: E402
from routes.fake_data import FIELDS, csv_safe  # noqa: E402
from routes.messaging import normalize_number, sms_segments  # noqa: E402

# The app under test uses its own throw-away database and secret key.
app = create_app({
    "DATABASE": os.path.join(tempfile.mkdtemp(), "test.db"),
    "SECRET_KEY": "test-secret",
    "TESTING": True,
})

PASSWORD = "correct horse battery"


def make_client(username):
    client = app.test_client()
    res = client.post("/api/register", json={"username": username, "password": PASSWORD})
    assert res.status_code == 201, res.get_json()
    return client


class AuthTests(unittest.TestCase):
    def test_password_is_hashed_and_salted(self):
        make_client("alice_a")
        make_client("alice_b")
        conn = sqlite3.connect(app.config["DATABASE"])
        hashes = [r[0] for r in conn.execute(
            "SELECT password_hash FROM users WHERE username IN ('alice_a','alice_b')")]
        conn.close()
        self.assertEqual(len(hashes), 2)
        for h in hashes:
            self.assertTrue(h.startswith("pbkdf2_sha256$"))
            self.assertNotIn(PASSWORD, h)
        self.assertNotEqual(hashes[0], hashes[1], "same password must hash differently (per-user salt)")

    def test_login_logout_flow(self):
        make_client("bob_login")
        c = app.test_client()
        bad = c.post("/api/login", json={"username": "bob_login", "password": "wrong-password"})
        self.assertEqual(bad.status_code, 401)
        ghost = c.post("/api/login", json={"username": "nobody_here", "password": PASSWORD})
        self.assertEqual(ghost.status_code, 401)
        self.assertEqual(bad.get_json(), ghost.get_json(), "do not reveal which usernames exist")
        ok = c.post("/api/login", json={"username": "BOB_LOGIN", "password": PASSWORD})
        self.assertEqual(ok.status_code, 200, "usernames are case-insensitive")
        self.assertEqual(c.get("/api/stats").status_code, 200)
        c.post("/api/logout")
        self.assertEqual(c.get("/api/stats").status_code, 401)

    def test_validation_and_duplicates(self):
        c = app.test_client()
        self.assertEqual(c.post("/api/register", json={"username": "ab", "password": PASSWORD}).status_code, 400)
        self.assertEqual(c.post("/api/register", json={"username": "good_name", "password": "short"}).status_code, 400)
        self.assertEqual(c.post("/api/register", json={"username": "bad name!", "password": PASSWORD}).status_code, 400)
        make_client("dupe_user")
        self.assertEqual(c.post("/api/register", json={"username": "Dupe_User", "password": PASSWORD}).status_code, 409)

    def test_pages_and_api_require_login(self):
        c = app.test_client()
        r = c.get("/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])
        for method, path in [("get", "/api/urls"), ("post", "/api/shorten"), ("get", "/api/fake-data"),
                             ("post", "/api/fake-data/generate"), ("get", "/api/fake-data/export"),
                             ("post", "/api/messages/send"), ("get", "/api/messages"), ("get", "/api/stats")]:
            self.assertEqual(getattr(c, method)(path).status_code, 401, path)


class UrlTests(unittest.TestCase):
    def setUp(self):
        self.c = make_client(f"url_{self.id().split('.')[-1][:20]}")

    def test_base62_random_and_alias(self):
        a = self.c.post("/api/shorten", json={"url": "https://example.com/a"}).get_json()
        b = self.c.post("/api/shorten", json={"url": "https://example.com/b"}).get_json()
        self.assertNotEqual(a["short_code"], b["short_code"])
        self.assertGreaterEqual(len(a["short_code"]), 6)
        r = self.c.post("/api/shorten", json={"url": "https://example.com/c", "mode": "random"}).get_json()
        self.assertEqual(len(r["short_code"]), 6)
        al = self.c.post("/api/shorten", json={"url": "https://example.com/d", "custom_alias": "my-link_1"})
        self.assertEqual(al.status_code, 201)
        dup = self.c.post("/api/shorten", json={"url": "https://example.com/e", "custom_alias": "my-link_1"})
        self.assertEqual(dup.status_code, 409)

    def test_rejects_bad_urls_and_aliases(self):
        for bad in ["javascript:alert(1)", "data:text/html,hi", "file:///etc/passwd", "ftp://x.com",
                    "example.com", "https://", "https://exa mple.com", "", "http://" + "a" * 3000 + ".com"]:
            res = self.c.post("/api/shorten", json={"url": bad})
            self.assertEqual(res.status_code, 400, bad)
        for alias in ["ab", "has space", "api", "LOGIN", "x" * 33, "bad/slash"]:
            res = self.c.post("/api/shorten", json={"url": "https://example.com", "custom_alias": alias})
            self.assertEqual(res.status_code, 400, alias)

    def test_redirect_counts_and_logs_clicks(self):
        code = self.c.post("/api/shorten", json={"url": "https://example.com/target"}).get_json()["short_code"]
        anon = app.test_client()            # redirect works without logging in
        for _ in range(3):
            res = anon.get("/" + code, headers={"Referer": "https://school.test/", "User-Agent": "UnitTest/1.0"})
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers["Location"], "https://example.com/target")
        stats = self.c.get(f"/api/urls/{code}/stats").get_json()
        self.assertEqual(stats["total_clicks"], 3)
        self.assertEqual(len(stats["recent"]), 3)
        self.assertEqual(stats["recent"][0]["referrer"], "https://school.test/")
        self.assertEqual(stats["recent"][0]["user_agent"], "UnitTest/1.0")
        self.assertEqual(anon.get("/does-not-exist").status_code, 404)

    def test_users_cannot_touch_each_others_links(self):
        code = self.c.post("/api/shorten", json={"url": "https://example.com/mine"}).get_json()["short_code"]
        other = make_client("intruder_" + code[:8])
        self.assertEqual(other.get(f"/api/urls/{code}/stats").status_code, 404)
        self.assertEqual(other.delete(f"/api/urls/{code}").status_code, 404)
        self.assertNotIn(code, [u["short_code"] for u in other.get("/api/urls").get_json()["urls"]])
        self.assertEqual(self.c.delete(f"/api/urls/{code}").status_code, 200)
        self.assertEqual(app.test_client().get("/" + code).status_code, 404)


class FakeDataTests(unittest.TestCase):
    def setUp(self):
        self.c = make_client(f"fake_{self.id().split('.')[-1][:20]}")

    def test_ten_records_with_ten_plus_fields_are_stored(self):
        res = self.c.post("/api/fake-data/generate", json={"count": 10, "locale": "en_PH"})
        self.assertEqual(res.status_code, 201)
        body = res.get_json()
        self.assertGreaterEqual(len(body["fields"]), 10)
        self.assertEqual(len(body["records"]), 10)
        for rec in body["records"]:
            self.assertTrue(all(str(rec[f]).strip() for f in body["fields"]), rec)
            self.assertRegex(rec["birthdate"], r"^\d{4}-\d{2}-\d{2}$")
            self.assertRegex(rec["mobile_number"], r"^\+63 9\d\d \d{3} \d{4}$")
        stored = self.c.get("/api/fake-data").get_json()           # read back from SQLite
        self.assertEqual(stored["total"], 10)
        self.assertEqual(len(stored["records"]), 10)
        self.assertEqual(self.c.get("/api/stats").get_json()["records"], 10)

    def test_count_limits_and_locale(self):
        for bad in [0, -1, 501, "abc", None, 2.5e9]:
            r = self.c.post("/api/fake-data/generate", json={"count": bad})
            self.assertEqual(r.status_code, 400, bad)
        self.assertEqual(self.c.post("/api/fake-data/generate", json={"count": 5, "locale": "xx_XX"}).status_code, 400)
        us = self.c.post("/api/fake-data/generate", json={"count": 3, "locale": "en_US"}).get_json()
        for rec in us["records"]:
            self.assertRegex(rec["mobile_number"], r"^\+1 [2-9]\d\d-[2-9]\d\d-\d{4}$")

    def test_export_and_clear(self):
        self.c.post("/api/fake-data/generate", json={"count": 12})
        csv_res = self.c.get("/api/fake-data/export?format=csv")
        self.assertIn("attachment", csv_res.headers["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(csv_res.get_data(as_text=True))))
        self.assertEqual(rows[0], FIELDS)
        self.assertEqual(len(rows) - 1, 12)
        self.assertTrue(rows[1][FIELDS.index("mobile_number")].startswith("+63"), "no apostrophe on phone numbers")
        self.assertEqual(len(self.c.get("/api/fake-data/export?format=json").get_json()), 12)
        self.assertEqual(self.c.get("/api/fake-data/export?format=xml").status_code, 400)
        self.assertEqual(self.c.delete("/api/fake-data").get_json()["deleted"], 12)
        self.assertEqual(self.c.get("/api/fake-data").get_json()["total"], 0)

    def test_records_are_private_per_user(self):
        self.c.post("/api/fake-data/generate", json={"count": 4})
        other = make_client("other_" + self.id().split(".")[-1][:15])
        self.assertEqual(other.get("/api/fake-data").get_json()["total"], 0)

    def test_csv_formula_guard(self):
        self.assertEqual(csv_safe("=1+1"), "'=1+1")
        self.assertEqual(csv_safe("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(csv_safe("+63 917 123 4567"), "+63 917 123 4567")


class MessagingTests(unittest.TestCase):
    def setUp(self):
        self.c = make_client(f"sms_{self.id().split('.')[-1][:20]}")

    def test_number_normalising(self):
        n = normalize_number
        self.assertEqual(n("0917 123 4567"), "+639171234567")
        self.assertEqual(n("+63 917-123-4567"), "+639171234567")
        self.assertEqual(n("639171234567"), "+639171234567")
        self.assertEqual(n("+1 (415) 555-0132"), "+14155550132")
        for bad in ["", None, "abc", "123", "0917", "+0", "09171234567890123"]:
            self.assertIsNone(n(bad), bad)

    def test_send_and_log_lifecycle(self):
        res = self.c.post("/api/messages/send", json={"recipient": "0917 555 1234", "message": "Hello there"})
        self.assertEqual(res.status_code, 201)
        body = res.get_json()
        self.assertEqual(body["recipient"], "+639175551234")
        self.assertIn(body["status"], ("delivered", "failed"))
        log = self.c.get("/api/messages").get_json()["messages"][0]
        self.assertIsNotNone(log["queued_at"])
        self.assertIsNotNone(log["sent_at"])
        self.assertIsNotNone(log["finished_at"])

    def test_forced_failure_and_filter(self):
        failed = self.c.post("/api/messages/send", json={"recipient": "09170000000", "message": "x"}).get_json()
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(failed["failure_reason"])
        only_failed = self.c.get("/api/messages?status=failed").get_json()["messages"]
        self.assertTrue(only_failed and all(m["status"] == "failed" for m in only_failed))
        self.assertEqual(self.c.get("/api/messages?status=bogus").status_code, 400)

    def test_validation_and_segments(self):
        self.assertEqual(self.c.post("/api/messages/send", json={"recipient": "nope", "message": "hi"}).status_code, 400)
        self.assertEqual(self.c.post("/api/messages/send", json={"recipient": "09171234567", "message": "  "}).status_code, 400)
        self.assertEqual(self.c.post("/api/messages/send", json={"recipient": "09171234567", "message": "x" * 641}).status_code, 400)
        self.assertEqual(sms_segments("x" * 160), 1)
        self.assertEqual(sms_segments("x" * 161), 2)
        self.assertEqual(sms_segments("x" * 307), 3)

    def test_bulk_send_uses_stored_records_and_templates(self):
        empty = self.c.post("/api/messages/bulk", json={"message": "Hi {first_name}"})
        self.assertEqual(empty.status_code, 400)
        self.c.post("/api/fake-data/generate", json={"count": 10, "locale": "en_PH"})
        res = self.c.post("/api/messages/bulk", json={"message": "Hi {first_name} {last_name}! {name} {unknown}"})
        self.assertEqual(res.status_code, 201)
        d = res.get_json()
        self.assertEqual(d["attempted"], 10)
        self.assertEqual(d["skipped"], 0, "every generated mobile number must be dispatchable")
        self.assertEqual(d["delivered"] + d["failed"], 10)
        msgs = self.c.get("/api/messages").get_json()["messages"]
        self.assertNotIn("{first_name}", msgs[0]["message_body"])
        self.assertIn("{unknown}", msgs[0]["message_body"])

    def test_html_in_message_is_stored_verbatim_as_data(self):
        payload = "<img src=x onerror=alert(1)>"
        self.c.post("/api/messages/send", json={"recipient": "09171234567", "message": payload})
        res = self.c.get("/api/messages")
        self.assertEqual(res.mimetype, "application/json")
        self.assertEqual(res.get_json()["messages"][0]["message_body"], payload)


class LegacyDatabaseTests(unittest.TestCase):
    def test_old_starter_database_is_moved_aside(self):
        path = os.path.join(tempfile.mkdtemp(), "old.db")
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, original_url TEXT, short_code TEXT UNIQUE, clicks INTEGER)")
        conn.commit()
        conn.close()
        init_db(path)
        conn = sqlite3.connect(path)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(urls)")]
        conn.close()
        self.assertIn("user_id", cols)
        self.assertEqual(len([f for f in os.listdir(os.path.dirname(path)) if ".legacy-" in f]), 1)


if __name__ == "__main__":
    unittest.main()
