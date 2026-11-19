"""3B.1  URL Shortener tab: create short links, copy/open them, view click stats, delete."""
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from routes import shortener as sh

from ..settings import BASE_URL
from ..widgets import make_table
from .base import BaseTab


class ShortenerTab(BaseTab):
    def __init__(self, master, db, user_id, on_change):
        super().__init__(master, db, user_id, on_change)
        self.url, self.alias, self.mode = tk.StringVar(), tk.StringVar(), tk.StringVar(value="base62")

        form = ttk.Frame(self)
        form.pack(fill="x")
        ttk.Label(form, text="Long URL").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(form, textvariable=self.url, width=60).grid(row=0, column=1, columnspan=3, sticky="we")
        ttk.Label(form, text="Custom alias (optional)").grid(row=1, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(form, textvariable=self.alias, width=24).grid(row=1, column=1, sticky="w")
        ttk.Label(form, text="Code type").grid(row=1, column=2, sticky="e", padx=4)
        ttk.Combobox(form, textvariable=self.mode, values=sh.CODE_MODES, width=10,
                     state="readonly").grid(row=1, column=3, sticky="w")
        ttk.Button(form, text="Shorten", command=self.shorten).grid(row=1, column=4, padx=8)
        form.columnconfigure(1, weight=1)

        columns = [("code", "Short code"), ("short", "Short URL"), ("original", "Original URL"),
                   ("clicks", "Clicks"), ("created", "Created")]
        table, self.tree = make_table(self, columns, [90, 190, 300, 60, 140])
        table.pack(fill="both", expand=True, pady=10)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x")
        for label, command in (("Copy short URL", self.copy), ("Open in browser", self.open_link),
                               ("Stats", self.stats), ("Delete", self.delete),
                               ("Refresh", self.refresh)):
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=4)
        self.refresh()

    def shorten(self):
        url, alias, mode = self.url.get().strip(), self.alias.get().strip(), self.mode.get()
        if not sh.is_valid_url(url):
            messagebox.showerror("Invalid URL", "Enter a valid http:// or https:// URL")
            return
        if alias:
            problem = sh.validate_alias(alias)
            if problem:
                messagebox.showerror("Invalid alias", problem)
                return
            code = sh.create_with_alias(self.db, self.user_id, url, alias)
            if code is None:
                self.db.rollback()          # a failed insert leaves a transaction open; the redirect
                                            # server in the background needs the database free
                messagebox.showerror("Alias in use", "Custom alias already in use")
                return
        elif mode == "random":
            code = sh.create_with_random_code(self.db, self.user_id, url)
            if code is None:
                self.db.rollback()
                messagebox.showerror("Error", "Could not generate a unique code, try again")
                return
        else:
            code = sh.create_with_base62_code(self.db, self.user_id, url)
        self.url.set("")
        self.alias.set("")
        self.refresh()
        self.on_change()
        messagebox.showinfo("Short link created", f"{BASE_URL}/{code}")

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        rows = self.db.execute(
            "SELECT original_url, short_code, created_at, clicks FROM urls "
            "WHERE user_id = ? ORDER BY id DESC LIMIT 200", (self.user_id,)).fetchall()
        for r in rows:
            self.tree.insert("", "end", values=(r["short_code"], f"{BASE_URL}/{r['short_code']}",
                                                r["original_url"], r["clicks"], r["created_at"]))

    def _selected_code(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Select a link", "Click a row in the table first.")
            return None
        return self.tree.item(selection[0])["values"][0]

    def copy(self):
        code = self._selected_code()
        if code is not None:
            self.clipboard_clear()
            self.clipboard_append(f"{BASE_URL}/{code}")

    def open_link(self):
        code = self._selected_code()
        if code is not None:
            webbrowser.open(f"{BASE_URL}/{code}")
            self.after(1500, self.refresh)          # show the new click count

    def stats(self):
        code = self._selected_code()
        if code is None:
            return
        link = self.db.execute(
            "SELECT id, original_url, clicks, created_at FROM urls WHERE short_code = ? AND user_id = ?",
            (str(code), self.user_id)).fetchone()
        if not link:
            return
        by_day = self.db.execute(
            "SELECT date(clicked_at) AS day, COUNT(*) AS n FROM url_clicks WHERE url_id = ? "
            "GROUP BY day ORDER BY day DESC LIMIT 7", (link["id"],)).fetchall()
        recent = self.db.execute(
            "SELECT clicked_at, referrer FROM url_clicks WHERE url_id = ? ORDER BY id DESC LIMIT 10",
            (link["id"],)).fetchall()
        text = [f"Short code: {code}", f"Original: {link['original_url']}",
                f"Total clicks: {link['clicks']}", f"Created: {link['created_at']}", "",
                "Clicks per day:"]
        text += [f"  {r['day']}: {r['n']}" for r in by_day] or ["  (no clicks yet)"]
        text += ["", "Recent clicks:"]
        text += [f"  {r['clicked_at']}  {r['referrer'] or '(no referrer)'}" for r in recent] or ["  (none)"]
        messagebox.showinfo("Link stats", "\n".join(text))

    def delete(self):
        code = self._selected_code()
        if code is None or not messagebox.askyesno("Delete link", f"Delete short link '{code}'?"):
            return
        self.db.execute("DELETE FROM urls WHERE short_code = ? AND user_id = ?",
                        (str(code), self.user_id))
        self.db.commit()
        self.refresh()
        self.on_change()
