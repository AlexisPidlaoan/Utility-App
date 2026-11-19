"""Tkinter desktop GUI for the Utility Suite. Start it with `python gui.py`.

Layout (each file has one job):

    ui/
        settings.py       constants: host/port, window title and size
        db.py             SQLite connection (same database file as the web version)
        server.py         background server so short links redirect in a browser
        widgets.py        shared widgets (the scrollable table)
        login.py          login / register screen
        main_frame.py     header + notebook that holds the tabs
        window.py         the App window: starts services, switches login <-> main
        tabs/
            base.py       BaseTab: gives every tab db, user_id, on_change
            shortener.py  3B.1 URL shortener
            sms.py        3B.2 SMS & messaging
            fake_data.py  3B.3 fake data generator

The GUI contains no business rules of its own. It calls the same functions the web routes use:
security.py (hashing), routes/shortener.py, routes/messaging.py, routes/fake_data.py.
"""
