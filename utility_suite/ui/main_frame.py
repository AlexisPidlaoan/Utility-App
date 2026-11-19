"""The window shown after login: a header (user, totals, log out) and one tab per tool."""
import tkinter as tk
from tkinter import ttk

from .tabs.fake_data import FakeDataTab
from .tabs.shortener import ShortenerTab
from .tabs.sms import SmsTab


class MainFrame(ttk.Frame):
    STATS = (("Links", "SELECT COUNT(*) FROM urls WHERE user_id = ?"),
             ("Clicks", "SELECT COALESCE(SUM(clicks), 0) FROM urls WHERE user_id = ?"),
             ("Records", "SELECT COUNT(*) FROM fake_records WHERE user_id = ?"),
             ("Messages", "SELECT COUNT(*) FROM message_logs WHERE user_id = ?"))

    def __init__(self, master, db, user_id, username, on_logout):
        super().__init__(master, padding=8)
        self.db, self.user_id = db, user_id
        self.summary = tk.StringVar()

        bar = ttk.Frame(self)
        bar.pack(fill="x")
        ttk.Label(bar, text=f"Signed in as {username}", font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Button(bar, text="Log out", command=on_logout).pack(side="right")
        ttk.Label(bar, textvariable=self.summary).pack(side="right", padx=16)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, pady=(8, 0))
        self.shortener = ShortenerTab(notebook, db, user_id, self.update_summary)
        self.fake = FakeDataTab(notebook, db, user_id, self.update_summary)
        self.sms = SmsTab(notebook, db, user_id, self.update_summary)
        notebook.add(self.shortener, text="URL Shortener")
        notebook.add(self.fake, text="Fake Data")
        notebook.add(self.sms, text="SMS & Messaging")
        notebook.bind("<<NotebookTabChanged>>", lambda _e: self.refresh_all())
        self.update_summary()

    def update_summary(self):
        counts = [f"{name}: {self.db.execute(sql, (self.user_id,)).fetchone()[0]}"
                  for name, sql in self.STATS]
        self.summary.set("   ".join(counts))

    def refresh_all(self):
        # Bulk send needs the latest records and a browser visit changes click counts.
        self.shortener.refresh()
        self.update_summary()
