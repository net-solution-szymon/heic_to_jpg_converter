"""The application window class.

``tkinterdnd2.Tk()`` is a plain Tk widget: it has no ``fg_color`` and cannot
host customtkinter's styling API directly. Mixing ``customtkinter.CTk`` with
tkinterdnd2's ``DnDWrapper`` gives a root that does both - this is the only
place where the two libraries meet.
"""
from __future__ import annotations

import customtkinter as ctk
from tkinterdnd2.TkinterDnD import DnDWrapper, _require


class AppWindow(ctk.CTk, DnDWrapper):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Loads the tkdnd Tcl extension into this interpreter and enables the
        # drop_target_register / dnd_bind methods on every widget.
        self.TkdndVersion = _require(self)
