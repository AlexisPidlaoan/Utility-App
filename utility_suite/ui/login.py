"""Login and registration screen. Passwords are checked with security.py (PBKDF2 + salt)."""
import sqlite3
import tkinter as tk
from tkinter import ttk

from routes.auth import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, USERNAME_RE
from security import DUMMY_HASH, hash_password, verify_password


class LoginFrame(ttk.Frame):
    def __init__(self, master, db, on_success):
        super().__init__(master, padding=30)
        self.db, self.on_success = db, on_success
        self.username, self.password = tk.StringVar(), tk.StringVar()

        ttk.Label(self, text="Utility Suite", font=("Segoe UI", 20, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(0, 4))
        ttk.Label(self, text="Log in or create an account").grid(row=1, column=0, columnspan=2, pady=(0, 16))

        ttk.Label(self, text="Username").grid(row=2, column=0, sticky="e", padx=6, pady=4)
        self.user_entry = ttk.Entry(self, textvariable=self.username, width=28)
        self.user_entry.grid(row=2, column=1, pady=4)
        ttk.Label(self, text="Password").grid(row=3, column=0, sticky="e", padx=6, pady=4)
        pw_entry = ttk.Entry(self, textvariable=self.password, show="*", width=28)
        pw_entry.grid(row=3, column=1, pady=4)

        buttons = ttk.Frame(self)
        buttons.grid(row=4, column=0, columnspan=2, pady=16)
        ttk.Button(buttons, text="Log in", command=self.login).pack(side="left", padx=6)
        ttk.Button(buttons, text="Register", command=self.register).pack(side="left", padx=6)

        self.error = ttk.Label(self, foreground="#b00020", wraplength=300)
        self.error.grid(row=5, column=0, columnspan=2)

        self.user_entry.focus()
        for widget in (self.user_entry, pw_entry):
            widget.bind("<Return>", lambda _e: self.login())

    def _credentials(self):
        return self.username.get().strip(), self.password.get()

    def login(self):
        username, password = self._credentials()
        user = self.db.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?", (username,)).fetchone()
        # Always verify a hash, even for unknown users, so timing does not reveal which names exist.
        stored = user["password_hash"] if user else DUMMY_HASH
        if not (verify_password(password, stored) and user):
            self.error.config(text="Invalid username or password")
            return
        self.on_success(user["id"], user["username"])

    def register(self):
        username, password = self._credentials()
        if not USERNAME_RE.fullmatch(username):
            self.error.config(text="Username must be 3-30 characters: letters, numbers, underscore")
            return
        if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
            self.error.config(
                text=f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters")
            return
        try:
            cur = self.db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                                  (username, hash_password(password)))
            self.db.commit()
        except sqlite3.IntegrityError:
            self.db.rollback()              # release the write lock the failed insert left open
            self.error.config(text="Username is already taken")
            return
        self.on_success(cur.lastrowid, username)
