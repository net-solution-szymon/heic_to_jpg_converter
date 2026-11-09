"""Styled modal dialogs.

Tkinter's stock message boxes look like Windows 95 next to a dark modern UI, so
the app brings its own. Everything returns a plain value and blocks until the
user decides.
"""
from __future__ import annotations

import customtkinter as ctk

from . import theme
from .theme import Palette


class ModalDialog(ctk.CTkToplevel):
    """A modal card with a message and up to three buttons."""

    def __init__(self, master, title: str, message: str,
                 buttons: list[tuple[str, str, str]] | None = None,
                 kind: str = "info", width: int = 470, extra=None,
                 cancel_value=None):
        super().__init__(master)
        self.result: str | None = cancel_value
        self._cancel_value = cancel_value

        self.title(title)
        self.configure(fg_color=Palette.bg)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        accent = {
            "info": Palette.accent,
            "warning": Palette.warning,
            "error": Palette.danger,
            "success": Palette.success,
            "question": Palette.accent,
        }.get(kind, Palette.accent)
        # Drawn icons, not unicode glyphs: "⚠"/"✕" render as blank boxes in
        # fonts that lack them, which looks broken on a paid product.
        icon_name = theme.ICON_FOR_KIND.get(kind, "info")

        outer = ctk.CTkFrame(self, fg_color=Palette.surface, corner_radius=theme.RADIUS,
                             border_width=1, border_color=Palette.border)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        body = ctk.CTkFrame(outer, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=(22, 18))

        head = ctk.CTkFrame(body, fg_color="transparent")
        head.pack(fill="x", anchor="w")

        ctk.CTkLabel(head, text="", image=theme.icon(icon_name, 22, accent),
                     width=30).pack(side="left", anchor="n", pady=(2, 0))
        ctk.CTkLabel(head, text=title, font=theme.font(16, "bold"),
                     text_color=Palette.text, justify="left", anchor="w",
                     wraplength=width - 90).pack(side="left", anchor="w", padx=(8, 0))

        ctk.CTkLabel(body, text=message, font=theme.font(13),
                     text_color=Palette.text_muted, justify="left", anchor="w",
                     wraplength=width - 70).pack(fill="x", pady=(12, 0))

        if extra is not None:  # optional input widget supplied by the caller
            extra.pack(fill="x", pady=(14, 0))

        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=(22, 0))

        for label, value, style in (buttons or [("OK", "ok", "primary")]):
            if style == "primary":
                button = theme.primary_button(row, label, lambda v=value: self._choose(v))
            elif style == "danger":
                button = theme.ghost_button(
                    row, label, lambda v=value: self._choose(v),
                    fg_color=Palette.danger, hover_color="#ff7878",
                    text_color="#ffffff", border_width=0)
            else:
                button = theme.ghost_button(row, label, lambda v=value: self._choose(v))
            button.pack(side="right", padx=(8, 0))

        self.bind("<Escape>", lambda _event: self._on_close())
        self.bind("<Return>", lambda _event: self._choose(
            (buttons or [("OK", "ok", "primary")])[-1][1]))

        self._centre(master, width)
        self.after(60, self._grab)

    # ------------------------------------------------------------------ #
    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except Exception:  # pragma: no cover - window already gone
            pass

    def _centre(self, master, width: int) -> None:
        self.update_idletasks()
        height = max(self.winfo_reqheight(), 150)
        try:
            if master is not None and master.winfo_viewable():
                x = master.winfo_rootx() + (master.winfo_width() - width) // 2
                y = master.winfo_rooty() + (master.winfo_height() - height) // 3
            else:
                raise RuntimeError
        except Exception:
            x = (self.winfo_screenwidth() - width) // 2
            y = (self.winfo_screenheight() - height) // 3
        x = max(0, x)
        y = max(0, y)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _choose(self, value: str) -> None:
        self.result = value
        self._close()

    def _on_close(self) -> None:
        self.result = self._cancel_value
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


# --------------------------------------------------------------------------- #
# convenience wrappers
# --------------------------------------------------------------------------- #
def show_message(master, title: str, message: str, kind: str = "info") -> None:
    ModalDialog(master, title, message, [("OK", "ok", "primary")], kind=kind).show()


def ask_choice(master, title: str, message: str,
               options: list[tuple[str, str]], kind: str = "question", **kwargs):
    """options = [(label, value), ...].

    The FIRST entry is the recommended action: it is highlighted and lands on
    the right, where users expect the primary button. The last entry is what
    Escape and the window close button return (usually "exit"/"cancel").

    Extra keyword arguments (for example ``width``) go straight to the dialog;
    the support prompt needs a wider window than the default to fit four
    buttons in one row without clipping the last one.
    """
    buttons = [(label, value, "primary" if index == 0 else "ghost")
               for index, (label, value) in enumerate(options)]
    return ModalDialog(master, title, message, buttons, kind=kind,
                       cancel_value=options[-1][1] if options else None,
                       **kwargs).show()


def ask_text(master, title: str, message: str, initial: str = "",
             placeholder: str = "") -> str | None:
    entry = ctk.CTkEntry(master, height=40, font=theme.font(14),
                         fg_color=Palette.surface_alt, border_color=Palette.border,
                         text_color=Palette.text, placeholder_text=placeholder,
                         corner_radius=theme.RADIUS_SMALL)
    if initial:
        entry.insert(0, initial)

    dialog = ModalDialog(
        master, title, message,
        [("Anuluj", "cancel", "ghost"), ("Zatwierdź", "ok", "primary")],
        kind="question", extra=entry, cancel_value=None,
    )

    def submit() -> None:
        dialog._choose("ok")

    entry.bind("<Return>", lambda _event: submit())

    value = dialog.show()
    if value != "ok":
        return None
    text = entry.get().strip()
    return text or None


# --------------------------------------------------------------------------- #
# read-only text window (licence, third-party notices, about)
# --------------------------------------------------------------------------- #
def show_text(master, title: str, text: str, width: int = 820, height: int = 620,
              buttons: list[tuple[str, str, str]] | None = None,
              kind: str = "info"):
    """A scrollable window with long read-only text.

    Used for the licence and the library notices, which are thousands of
    characters long and must not be abbreviated - showing them in full is a
    licence obligation, not a courtesy.
    """
    window = ctk.CTkToplevel(master)
    window.title(title)
    window.configure(fg_color=Palette.bg)
    window.minsize(560, 380)

    accent = {"info": Palette.accent, "warning": Palette.warning}.get(kind, Palette.accent)

    head = ctk.CTkFrame(window, fg_color="transparent")
    head.pack(fill="x", padx=22, pady=(20, 8))
    ctk.CTkLabel(head, text="", image=theme.icon(theme.ICON_FOR_KIND.get(kind, "info"),
                                                 20, accent), width=26).pack(side="left")
    ctk.CTkLabel(head, text=title, font=theme.font(16, "bold"),
                 text_color=Palette.text).pack(side="left", padx=(8, 0))

    box = ctk.CTkTextbox(window, font=theme.font(12), fg_color=Palette.surface,
                         border_color=Palette.border, border_width=1,
                         text_color=Palette.text_muted, wrap="word",
                         corner_radius=theme.RADIUS_SMALL)
    box.pack(fill="both", expand=True, padx=22, pady=(4, 14))
    box.insert("1.0", text)
    # Read-only, but still selectable: people copy licence text into emails.
    box.configure(state="disabled")

    result: dict = {"value": None}

    def choose(value: str) -> None:
        result["value"] = value
        window.destroy()

    row = ctk.CTkFrame(window, fg_color="transparent")
    row.pack(fill="x", padx=22, pady=(0, 20))
    for label, value, style in (buttons or [("Zamknij", "close", "primary")]):
        if style == "primary":
            button = theme.primary_button(row, label, lambda v=value: choose(v))
        else:
            button = theme.ghost_button(row, label, lambda v=value: choose(v))
        button.pack(side="right", padx=(8, 0))

    window.protocol("WM_DELETE_WINDOW", lambda: choose("close"))
    window.bind("<Escape>", lambda _event: choose("close"))

    window.update_idletasks()
    x = (window.winfo_screenwidth() - width) // 2
    y = (window.winfo_screenheight() - height) // 3
    window.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    try:
        window.grab_set()
        window.focus_force()
    except Exception:  # pragma: no cover - window already gone
        pass

    master.wait_window(window)
    return result["value"]
