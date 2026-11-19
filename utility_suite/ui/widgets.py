"""Small reusable Tkinter widgets shared by the tabs."""
from tkinter import ttk


def make_table(parent, columns, widths):
    """A Treeview with a vertical scrollbar.

    `columns` is a list of (key, heading) pairs. Returns (frame, tree): pack the frame,
    fill the tree.
    """
    frame = ttk.Frame(parent)
    tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", height=10)
    for (key, heading), width in zip(columns, widths):
        tree.heading(key, text=heading)
        tree.column(key, width=width, anchor="w")
    bar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=bar.set)
    tree.pack(side="left", fill="both", expand=True)
    bar.pack(side="right", fill="y")
    return frame, tree


def set_columns(tree, columns, widths):
    """Change which columns a Treeview shows. `widths` maps column key -> pixel width.

    Used by the Fake Data tab, whose columns depend on which fields the stored records contain.
    Clear the rows before calling this, then insert rows that match the new columns.
    """
    tree["columns"] = [key for key, _heading in columns]
    for key, heading in columns:
        tree.heading(key, text=heading)
        tree.column(key, width=widths.get(key, 120), anchor="w")
