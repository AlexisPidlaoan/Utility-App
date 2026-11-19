"""3B.3  Fake Data tab: generate 11-field records, store them in SQLite, export CSV/JSON."""
import tkinter as tk
import uuid
from tkinter import filedialog, messagebox, ttk

from routes import fake_data as fd

from ..widgets import make_table
from .base import BaseTab


class FakeDataTab(BaseTab):
    def __init__(self, master, db, user_id, on_change):
        super().__init__(master, db, user_id, on_change)
        self.count, self.locale = tk.StringVar(value="10"), tk.StringVar(value="en_PH")
        self.total = tk.StringVar()

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Records").pack(side="left", padx=4)
        ttk.Spinbox(top, from_=1, to=fd.MAX_RECORDS, textvariable=self.count, width=6).pack(side="left")
        ttk.Label(top, text="Locale").pack(side="left", padx=(12, 4))
        ttk.Combobox(top, textvariable=self.locale, values=list(fd.LOCALES), width=8,
                     state="readonly").pack(side="left")
        ttk.Button(top, text="Generate and save", command=self.generate).pack(side="left", padx=10)
        ttk.Button(top, text="Export CSV", command=lambda: self.export("csv")).pack(side="left", padx=2)
        ttk.Button(top, text="Export JSON", command=lambda: self.export("json")).pack(side="left", padx=2)
        ttk.Button(top, text="Clear all", command=self.clear).pack(side="left", padx=2)
        ttk.Label(top, textvariable=self.total).pack(side="right")

        columns = [(f, f.replace("_", " ").title()) for f in fd.FIELDS]
        widths = [90, 90, 60, 90, 40, 220, 100, 130, 180, 140, 140]
        table, self.tree = make_table(self, columns, widths)
        xbar = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=xbar.set)
        table.pack(fill="both", expand=True, pady=(10, 0))
        xbar.pack(fill="x")
        self.refresh()

    def generate(self):
        try:
            count = int(self.count.get())
        except ValueError:
            messagebox.showerror("Invalid number", "Records must be a whole number")
            return
        if not 1 <= count <= fd.MAX_RECORDS:
            messagebox.showerror("Invalid number", f"Records must be between 1 and {fd.MAX_RECORDS}")
            return
        locale = self.locale.get()
        fk = fd.get_faker(locale)
        records = [fd.make_record(fk, locale) for _ in range(count)]
        fd._save_records(self.db, self.user_id, uuid.uuid4().hex[:8], records)
        self.refresh()
        self.on_change()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        total = self.db.execute("SELECT COUNT(*) FROM fake_records WHERE user_id = ?",
                                (self.user_id,)).fetchone()[0]
        rows = self.db.execute(
            f"SELECT {', '.join(fd.FIELDS)} FROM fake_records WHERE user_id = ? "
            f"ORDER BY id DESC LIMIT {fd.LIST_LIMIT}", (self.user_id,)).fetchall()
        for r in rows:
            self.tree.insert("", "end", values=[r[f] for f in fd.FIELDS])
        self.total.set(f"{total} stored (showing latest {min(total, fd.LIST_LIMIT)})")

    def export(self, fmt):
        rows = self.db.execute(
            f"SELECT {', '.join(fd.FIELDS)} FROM fake_records WHERE user_id = ? ORDER BY id",
            (self.user_id,)).fetchall()
        if not rows:
            messagebox.showinfo("Nothing to export", "Generate some records first.")
            return
        path = filedialog.asksaveasfilename(defaultextension=f".{fmt}", initialfile=f"fake_records.{fmt}",
                                            filetypes=[(fmt.upper(), f"*.{fmt}")])
        if path:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(fd.EXPORT_FORMATS[fmt][0](rows))
            messagebox.showinfo("Exported", f"Saved {len(rows)} records to\n{path}")

    def clear(self):
        if messagebox.askyesno("Clear records", "Delete all your stored fake records?"):
            self.db.execute("DELETE FROM fake_records WHERE user_id = ?", (self.user_id,))
            self.db.commit()
            self.refresh()
            self.on_change()
