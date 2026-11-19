"""3B.2  SMS & Messaging tab (simulated): single send, bulk send with templates, message log."""
import tkinter as tk
from tkinter import messagebox, ttk

from routes import messaging as msg

from ..widgets import make_table
from .base import BaseTab


class SmsTab(BaseTab):
    def __init__(self, master, db, user_id, on_change):
        super().__init__(master, db, user_id, on_change)
        self.recipient, self.filter = tk.StringVar(), tk.StringVar(value="all")
        self.counter, self.result = tk.StringVar(), tk.StringVar()

        form = ttk.Frame(self)
        form.pack(fill="x")
        ttk.Label(form, text="Mobile number").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(form, textvariable=self.recipient, width=24).grid(row=0, column=1, sticky="w")
        ttk.Label(form, text="e.g. 09171234567 or +639171234567").grid(row=0, column=2, sticky="w", padx=8)
        ttk.Label(form, text="Message").grid(row=1, column=0, sticky="ne", padx=4, pady=3)
        self.body = tk.Text(form, width=60, height=4, wrap="word")
        self.body.grid(row=1, column=1, columnspan=2, sticky="we")
        self.body.bind("<KeyRelease>", lambda _e: self.update_counter())
        ttk.Label(form, textvariable=self.counter).grid(row=2, column=1, sticky="w")
        form.columnconfigure(2, weight=1)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=6)
        ttk.Button(actions, text="Send", command=self.send).pack(side="left", padx=4)
        ttk.Button(actions, text=f"Bulk send to latest {msg.BULK_LIMIT} stored contacts "
                                 "({first_name}, {last_name}, {name})",
                   command=self.bulk).pack(side="left", padx=4)
        ttk.Label(actions, textvariable=self.result).pack(side="left", padx=10)

        log_bar = ttk.Frame(self)
        log_bar.pack(fill="x")
        ttk.Label(log_bar, text="Message log, filter").pack(side="left", padx=4)
        box = ttk.Combobox(log_bar, textvariable=self.filter, values=["all", *msg.STATUSES],
                           width=10, state="readonly")
        box.pack(side="left")
        box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Button(log_bar, text="Refresh", command=self.refresh).pack(side="left", padx=6)

        columns = [("id", "#"), ("to", "Recipient"), ("status", "Status"), ("seg", "Parts"),
                   ("body", "Message"), ("reason", "Failure reason"), ("time", "Queued")]
        table, self.tree = make_table(self, columns, [40, 120, 80, 50, 300, 160, 140])
        table.pack(fill="both", expand=True, pady=6)
        self.update_counter()
        self.refresh()

    def _text(self):
        return self.body.get("1.0", "end").strip()

    def update_counter(self):
        text = self._text()
        self.counter.set(f"{len(text)}/{msg.MAX_MESSAGE_LEN} characters, "
                         f"{msg.sms_segments(text)} SMS part(s)")

    def send(self):
        number, text = msg.normalize_number(self.recipient.get()), self._text()
        if not number:
            messagebox.showerror("Invalid number", "Enter a valid mobile number "
                                 "(e.g. 09171234567 or +639171234567)")
            return
        problem = msg.validate_message(text)
        if problem:
            messagebox.showerror("Invalid message", problem)
            return
        status, reason = msg.dispatch_message(self.db, self.user_id, number, text)
        self.db.commit()
        self.result.set(f"{number}: {status}" + (f" ({reason})" if reason else ""))
        self.refresh()
        self.on_change()

    def bulk(self):
        template = self._text()
        problem = msg.validate_message(template)
        if problem:
            messagebox.showerror("Invalid message", problem)
            return
        contacts = self.db.execute(
            "SELECT first_name, last_name, mobile_number FROM fake_records WHERE user_id = ? "
            f"ORDER BY id DESC LIMIT {msg.BULK_LIMIT}", (self.user_id,)).fetchall()
        if not contacts:
            messagebox.showinfo("No contacts", "No stored fake records yet. Generate some first.")
            return
        if not messagebox.askyesno("Bulk send", f"Send this message to {len(contacts)} contacts?"):
            return
        summary = {"delivered": 0, "failed": 0, "skipped": 0}
        for contact in contacts:
            number = msg.normalize_number(contact["mobile_number"])
            if not number:
                summary["skipped"] += 1
                continue
            body = msg.personalize(template, contact)[:msg.MAX_MESSAGE_LEN]
            status, _reason = msg.dispatch_message(self.db, self.user_id, number, body)
            summary[status] += 1
        self.db.commit()
        self.result.set("Bulk: " + ", ".join(f"{v} {k}" for k, v in summary.items()))
        self.refresh()
        self.on_change()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        query = ("SELECT id, recipient, message_body, segments, status, failure_reason, queued_at "
                 "FROM message_logs WHERE user_id = ?")
        params = [self.user_id]
        if self.filter.get() != "all":
            query += " AND status = ?"
            params.append(self.filter.get())
        for r in self.db.execute(query + " ORDER BY id DESC LIMIT 100", params):
            self.tree.insert("", "end", values=(r["id"], r["recipient"], r["status"], r["segments"],
                                                r["message_body"], r["failure_reason"] or "",
                                                r["queued_at"]))
