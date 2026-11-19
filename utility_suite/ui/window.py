"""The application window: starts the services, then swaps between the login and main screens."""
import tkinter as tk
from tkinter import messagebox

from . import settings
from .db import connect
from .login import LoginFrame
from .main_frame import MainFrame
from .server import start_redirect_server


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(settings.WINDOW_TITLE)
        self.geometry(settings.WINDOW_SIZE)
        self.minsize(*settings.MIN_SIZE)
        self.server = start_redirect_server()
        self.db = connect()
        self.current = None
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_login()
        if self.server is None:
            messagebox.showwarning(
                "Redirect server not started",
                f"Port {settings.PORT} is busy, so short links will not open in a browser.\n"
                "Everything else still works.")

    def _swap(self, frame):
        if self.current is not None:
            self.current.destroy()
        self.current = frame
        frame.pack(fill="both", expand=True)

    def show_login(self):
        self._swap(LoginFrame(self, self.db, self.show_main))

    def show_main(self, user_id, username):
        self._swap(MainFrame(self, self.db, user_id, username, self.show_login))

    def close(self):
        if self.server is not None:
            self.server.shutdown()
        self.db.close()
        self.destroy()
