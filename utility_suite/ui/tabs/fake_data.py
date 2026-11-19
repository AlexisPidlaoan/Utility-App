"""3B.3  Fake Data tab: pick up to 16 fields, generate records, store them in SQLite, export CSV/JSON."""
import tkinter as tk
import uuid
from tkinter import filedialog, messagebox, ttk

from routes import fake_data as fd

from ..widgets import make_table, set_columns
from .base import BaseTab

PICKER_COLUMNS = 4                      # checkboxes per row (16 fields -> 4 rows)
COLUMN_WIDTHS = {
    "first_name": 100, "last_name": 100, "full_name": 160, "sex": 60, "birthdate": 90, "age": 45,
    "civil_status": 90, "address": 260, "city": 110, "zip_code": 70, "country": 110,
    "mobile_number": 130, "email": 190, "username": 120, "job": 150, "company": 150,
}


class FakeDataTab(BaseTab):
    def __init__(self, master, db, user_id, on_change):
        super().__init__(master, db, user_id, on_change)
        self.count, self.locale = tk.StringVar(value="10"), tk.StringVar(value="en_PH")
        self.total, self.picked_text = tk.StringVar(), tk.StringVar()
        self.picked = {f: tk.BooleanVar(value=True) for f in fd.FIELDS}   # field -> ticked?

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

        self._build_picker()

        table, self.tree = make_table(self, [], [])
        xbar = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(xscrollcommand=xbar.set)
        table.pack(fill="both", expand=True, pady=(10, 0))
        xbar.pack(fill="x")
        self.update_picked_text()
        self.refresh()

    # ----- choosing fields -----
    def _build_picker(self):
        box = ttk.LabelFrame(self, text="Fields to generate", padding=8)
        box.pack(fill="x", pady=(10, 0))
        for index, field in enumerate(fd.FIELDS):
            ttk.Checkbutton(box, text=fd.FIELD_LABELS[field], variable=self.picked[field],
                            command=self.update_picked_text).grid(
                row=index // PICKER_COLUMNS, column=index % PICKER_COLUMNS, sticky="w", padx=10, pady=2)
        for column in range(PICKER_COLUMNS):
            box.columnconfigure(column, weight=1)

        bar = ttk.Frame(box)
        bar.grid(row=(len(fd.FIELDS) - 1) // PICKER_COLUMNS + 1, column=0, columnspan=PICKER_COLUMNS,
                 sticky="w", pady=(6, 0))
        ttk.Button(bar, text="Select all", command=lambda: self.set_all(True)).pack(side="left", padx=4)
        ttk.Button(bar, text="Clear selection", command=lambda: self.set_all(False)).pack(side="left", padx=4)
        ttk.Label(bar, textvariable=self.picked_text).pack(side="left", padx=12)

    def chosen_fields(self):
        return [f for f in fd.FIELDS if self.picked[f].get()]

    def set_all(self, ticked):
        for var in self.picked.values():
            var.set(ticked)
        self.update_picked_text()

    def update_picked_text(self):
        self.picked_text.set(f"{len(self.chosen_fields())} of {fd.MAX_FIELDS} fields selected")

    # ----- actions -----
    def generate(self):
        try:
            count = int(self.count.get())
        except ValueError:
            messagebox.showerror("Invalid number", "Records must be a whole number")
            return
        if not 1 <= count <= fd.MAX_RECORDS:
            messagebox.showerror("Invalid number", f"Records must be between 1 and {fd.MAX_RECORDS}")
            return
        fields, problem = fd.parse_fields(self.chosen_fields())
        if problem:
            messagebox.showerror("Choose fields", problem)
            return
        locale = self.locale.get()
        fk = fd.get_faker(locale)
        records = [fd.make_record(fk, locale, fields) for _ in range(count)]
        fd._save_records(self.db, self.user_id, uuid.uuid4().hex[:8], records, fields)
        self.refresh()
        self.on_change()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        total = self.db.execute("SELECT COUNT(*) FROM fake_records WHERE user_id = ?",
                                (self.user_id,)).fetchone()[0]
        rows = self.db.execute(
            f"SELECT {', '.join(fd.FIELDS)} FROM fake_records WHERE user_id = ? "
            f"ORDER BY id DESC LIMIT {fd.LIST_LIMIT}", (self.user_id,)).fetchall()
        columns = fd.used_fields(rows)              # show only the columns that hold data
        set_columns(self.tree, [(f, fd.FIELD_LABELS[f]) for f in columns], COLUMN_WIDTHS)
        for r in rows:
            self.tree.insert("", "end", values=["" if r[f] is None else r[f] for f in columns])
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
