-- Developer & Admin Utility Suite: database schema (SQLite)
-- Safe to re-run: every statement uses IF NOT EXISTS.

PRAGMA foreign_keys = ON;

-- ---------- Authentication ----------
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,              -- pbkdf2_sha256$iterations$salt$hash
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ---------- 3B.1 URL Shortener ----------
CREATE TABLE IF NOT EXISTS urls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_url TEXT NOT NULL,
    short_code   TEXT NOT NULL UNIQUE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    clicks       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS url_clicks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    url_id     INTEGER NOT NULL REFERENCES urls(id) ON DELETE CASCADE,
    clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    referrer   TEXT,
    user_agent TEXT
);
CREATE INDEX IF NOT EXISTS idx_url_clicks_url ON url_clicks(url_id);
CREATE INDEX IF NOT EXISTS idx_urls_user ON urls(user_id);

-- ---------- 3B.3 Fake Data Generation (11 stored fields) ----------
CREATE TABLE IF NOT EXISTS fake_records (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    batch_id      TEXT NOT NULL,
    first_name    TEXT NOT NULL,
    last_name     TEXT NOT NULL,
    sex           TEXT NOT NULL,
    birthdate     TEXT NOT NULL,              -- ISO date YYYY-MM-DD
    age           INTEGER NOT NULL,
    address       TEXT NOT NULL,
    city          TEXT NOT NULL,
    mobile_number TEXT NOT NULL,
    email         TEXT NOT NULL,
    job           TEXT NOT NULL,
    company       TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fake_user ON fake_records(user_id);

-- ---------- 3B.2 SMS & Messaging Dispatcher (simulated) ----------
CREATE TABLE IF NOT EXISTS message_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipient      TEXT NOT NULL,
    message_body   TEXT NOT NULL,
    segments       INTEGER NOT NULL DEFAULT 1,
    status         TEXT NOT NULL DEFAULT 'queued'
                   CHECK (status IN ('queued', 'sent', 'delivered', 'failed')),
    failure_reason TEXT,
    queued_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sent_at        TIMESTAMP,
    finished_at    TIMESTAMP                  -- delivered or failed time
);
CREATE INDEX IF NOT EXISTS idx_msg_user ON message_logs(user_id);
