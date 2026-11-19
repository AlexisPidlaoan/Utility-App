"""Base class for the tool tabs."""
from tkinter import ttk


class BaseTab(ttk.Frame):
    """Every tab gets the same three things:

    db         the shared SQLite connection
    user_id    the signed-in user (every query filters by it, so users only see their own data)
    on_change  called after the tab changes data, so the header totals update
    """

    def __init__(self, master, db, user_id, on_change):
        super().__init__(master, padding=10)
        self.db, self.user_id, self.on_change = db, user_id, on_change
