"""The main window: a modern, dark, drag & drop HEIC -> JPG converter."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter
from pathlib import Path
from tkinter import filedialog

from tkinterdnd2 import DND_FILES

from . import about, dialogs, support, telemetry, theme
from .converter import (
    CONVERTED,
    ERROR,
    SKIPPED,
    Options,
    Summary,
    collect_files,
    convert_files,
    parse_drop_list,
    register_heif,
)
from .theme import Palette

MAX_VISIBLE_ROWS = 400
ROW_BATCH = 40


class ConverterApp:
    def __init__(self, root, config, values):
        self.root = root
        # `config` is the user-editable config.py module; `values` is the
        # dictionary of remembered state (counters, preferences) from store.py.
        # Passing them in keeps this class free of any file or network access.
        self.config = config
        self.values = values
        # The window title belongs to the app, not to main.py - so it is also
        # correct when the app is built somewhere else (tests, tools).
        root.title(self._base_title())
        self.help_button = None
        self.files: list[Path] = []
        self.warnings: list[str] = []
        self.rows: dict[str, dict] = {}
        self.worker: threading.Thread | None = None
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.summary: Summary | None = None
        self.last_output_dir: Path | None = None
        self._icon = None
        self._closing = False
        self._pump_id = None
        self.last_error: str | None = None

        self.quality = tkinter.IntVar(value=90)
        self.keep_exif = tkinter.BooleanVar(value=True)
        self.overwrite = tkinter.BooleanVar(value=False)
        self.delete_original = tkinter.BooleanVar(value=False)
        self.recursive = tkinter.BooleanVar(value=True)
        self.output_mode = tkinter.StringVar(value="Obok oryginału")
        self.custom_output = tkinter.StringVar(value="")

        self._set_icon()
        self._build_ui()
        self._bind_shortcuts()
        self._update_convert_button()
        self._pump_id = self.root.after(120, self._pump_events)

    # ------------------------------------------------------------------ #
    # window chrome
    # ------------------------------------------------------------------ #
    def _set_icon(self) -> None:
        try:
            from PIL import Image, ImageDraw, ImageTk

            size = 64
            image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((2, 2, size - 3, size - 3), radius=14,
                                   fill=Palette.accent)
            # a simple "photo" glyph: sun + mountain
            draw.ellipse((14, 13, 24, 23), fill="#ffffff")
            draw.polygon([(8, 46), (26, 24), (40, 46)], fill="#dbe8ff")
            draw.polygon([(30, 46), (44, 30), (58, 46)], fill="#ffffff")
            self._icon = ImageTk.PhotoImage(image)
            self.root.iconphoto(True, self._icon)
        except Exception:  # pragma: no cover - purely cosmetic
            pass

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _e: self.pick_files())
        self.root.bind("<Control-O>", lambda _e: self.pick_files())
        self.root.bind("<Control-Shift-O>", lambda _e: self.pick_folder())
        self.root.bind("<Control-Return>", lambda _e: self.start_conversion())
        self.root.bind("<Escape>", lambda _e: self.cancel_conversion())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ #
    # layout
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        self.root.configure(fg_color=Palette.bg)
        self.root.grid_columnconfigure(0, weight=3, uniform="cols")
        self.root.grid_columnconfigure(1, weight=2, uniform="cols")
        self.root.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_left()
        self._build_right()
        self._build_statusbar()

    def _build_header(self) -> None:
        header = ctk_frame(self.root)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=theme.PAD,
                    pady=(theme.PAD, 8))
        header.grid_columnconfigure(0, weight=1)

        left = ctk_frame(header)
        left.grid(row=0, column=0, sticky="w")
        ctk_label(left, "HEIC → JPG", font=theme.font(22, "bold"),
                  text_color=Palette.text).pack(anchor="w")
        ctk_label(left, "Konwertuj zdjęcia z iPhone'a na uniwersalne pliki JPG",
                  font=theme.font(12), text_color=Palette.text_muted).pack(anchor="w")

        right = ctk_frame(header)
        right.grid(row=0, column=1, sticky="e")

        # The support button sits in plain sight on purpose: asking for money
        # only ever from a hidden menu would be worse than asking openly.
        self.support_button = theme.ghost_button(
            right, "\u2615 Postaw kawę", self.open_support,
            height=32, font=theme.font(12))
        self.support_button.pack(side="left", padx=(0, 8))
        self.help_button = theme.ghost_button(right, "Pomoc", self.open_help_menu,
                                              height=32, font=theme.font(12))
        self.help_button.pack(side="left")

    def _build_left(self) -> None:
        left = ctk_frame(self.root)
        left.grid(row=1, column=0, sticky="nsew", padx=(theme.PAD, 8), pady=8)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(1, weight=1)

        self._build_drop_zone(left)
        self._build_file_list(left)

    def _build_drop_zone(self, parent) -> None:
        # Tall enough for the icon, the two lines of text and the buttons row -
        # with grid_propagate(False) the height must be generous or content clips.
        self.drop = theme.card(parent, height=186)
        self.drop.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self.drop.grid_propagate(False)
        self.drop.grid_columnconfigure(0, weight=1)

        inner = ctk_frame(self.drop)
        inner.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        self.drop.grid_rowconfigure(0, weight=1)

        self.drop_icon = ctk_label(inner, "", image=theme.icon("drop", 36, Palette.accent))
        self.drop_icon.pack(pady=(18, 2))
        self.drop_title = ctk_label(inner, "Przeciągnij tutaj zdjęcia HEIC lub folder",
                                    font=theme.font(15, "bold"), text_color=Palette.text)
        self.drop_title.pack(pady=(2, 0))
        self.drop_hint = ctk_label(
            inner, "Obsługiwane: .heic, .heif · możesz wrzucić wiele plików naraz",
            font=theme.font(11), text_color=Palette.text_faint)
        self.drop_hint.pack(pady=(3, 12))

        buttons = ctk_frame(inner)
        buttons.pack(pady=(0, 14))
        theme.ghost_button(buttons, "Wybierz pliki", self.pick_files, height=34,
                           font=theme.font(12)).pack(side="left", padx=4)
        theme.ghost_button(buttons, "Wybierz folder", self.pick_folder, height=34,
                           font=theme.font(12)).pack(side="left", padx=4)

        self._register_drop(self.drop, inner, self.drop_icon, self.drop_title,
                            self.drop_hint, buttons)

    def _register_drop(self, *widgets) -> None:
        for widget in widgets:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self.on_drop)
                widget.dnd_bind("<<DropEnter>>", self._on_drop_enter)
                widget.dnd_bind("<<DropLeave>>", self._on_drop_leave)
            except Exception:  # pragma: no cover - widget without DnD support
                continue

    def _on_drop_enter(self, _event) -> None:
        self.drop.configure(border_color=Palette.accent, fg_color=Palette.accent_soft)
        self.drop_title.configure(text_color=Palette.text)

    def _on_drop_leave(self, _event) -> None:
        self.drop.configure(border_color=Palette.border, fg_color=Palette.surface)

    def _build_file_list(self, parent) -> None:
        card = theme.card(parent)
        card.grid(row=1, column=0, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)

        head = ctk_frame(card)
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 6))
        head.grid_columnconfigure(0, weight=1)

        self.files_title = ctk_label(head, "Brak plików", font=theme.font(14, "bold"),
                                     text_color=Palette.text)
        self.files_title.grid(row=0, column=0, sticky="w")
        self.files_subtitle = ctk_label(head, "Dodaj zdjęcia, aby rozpocząć",
                                        font=theme.font(11), text_color=Palette.text_faint)
        self.files_subtitle.grid(row=1, column=0, sticky="w")

        theme.ghost_button(head, "Wyczyść", self.clear_files, width=90, height=28,
                           font=theme.font(11)).grid(row=0, column=1, rowspan=2, sticky="e")

        ctk_separator = ctk_frame(card, fg_color=Palette.border, height=1, corner_radius=0)
        ctk_separator.grid(row=1, column=0, sticky="ew", padx=16)

        self.file_list = ctk_scrollable(card, fg_color="transparent")
        self.file_list.grid(row=2, column=0, sticky="nsew", padx=8, pady=(6, 12))
        self.file_list.grid_columnconfigure(0, weight=1)

        self.empty_hint = ctk_label(
            self.file_list,
            "Lista jest pusta.\n\nPrzeciągnij zdjęcia do pola powyżej\n"
            "albo użyj przycisków „Wybierz pliki” / „Wybierz folder”.",
            font=theme.font(12), text_color=Palette.text_faint, justify="center")
        self.empty_hint.grid(row=0, column=0, pady=60)

    def _build_right(self) -> None:
        right = ctk_frame(self.root)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, theme.PAD), pady=8)
        right.grid_columnconfigure(0, weight=1)

        self._build_options(right)
        self._build_actions(right)
        self._build_summary_card(right)
        right.grid_rowconfigure(2, weight=1)

    def _build_summary_card(self, parent) -> None:
        card = theme.card(parent)
        card.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)

        pad = ctk_frame(card)
        pad.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        pad.grid_columnconfigure(0, weight=1)

        theme.section_title(pad, "Ostatnia konwersja").grid(row=0, column=0, sticky="w")

        self.summary_big = ctk_label(pad, "—", font=theme.font(22, "bold"),
                                     text_color=Palette.text, anchor="w")
        self.summary_big.grid(row=1, column=0, sticky="w", pady=(6, 2))

        self.summary_lines = ctk_label(
            pad, "Wyniki pojawią się po pierwszej konwersji.",
            font=theme.font(11), text_color=Palette.text_faint,
            anchor="w", justify="left")
        self.summary_lines.grid(row=2, column=0, sticky="ew")

        pad.grid_rowconfigure(3, weight=1)

        ctk_label(pad,
                  "Ctrl+O pliki  ·  Ctrl+Shift+O folder\n"
                  "Ctrl+Enter konwertuj  ·  Esc anuluj",
                  font=theme.font(10), text_color=Palette.text_faint,
                  anchor="w", justify="left").grid(row=4, column=0, sticky="w",
                                                   pady=(10, 0))

    def _build_options(self, parent) -> None:
        card = theme.card(parent)
        card.grid(row=0, column=0, sticky="ew")
        card.grid_columnconfigure(0, weight=1)

        pad = ctk_frame(card)
        pad.grid(row=0, column=0, sticky="ew", padx=16, pady=14)
        pad.grid_columnconfigure(0, weight=1)

        theme.section_title(pad, "Ustawienia").grid(row=0, column=0, sticky="w")

        quality_row = ctk_frame(pad)
        quality_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        quality_row.grid_columnconfigure(0, weight=1)
        ctk_label(quality_row, "Jakość JPEG", font=theme.font(12),
                  text_color=Palette.text).grid(row=0, column=0, sticky="w")
        self.quality_label = ctk_label(quality_row, "90", font=theme.font(12, "bold"),
                                       text_color=Palette.accent)
        self.quality_label.grid(row=0, column=1, sticky="e")
        self.quality_slider = ctk_slider(
            pad, from_=50, to=100, number_of_steps=50, command=self._on_quality,
            progress_color=Palette.accent, button_color=Palette.accent,
            button_hover_color=Palette.accent_hover, fg_color=Palette.surface_high)
        self.quality_slider.set(90)
        self.quality_slider.grid(row=2, column=0, sticky="ew", pady=(4, 8))

        self._switch(pad, 3, "Zachowaj dane EXIF (data, model aparatu)",
                     self.keep_exif)
        self._switch(pad, 4, "Nadpisz istniejące pliki JPG", self.overwrite)
        self._switch(pad, 5, "Przeszukuj podfoldery", self.recursive)
        self._switch(pad, 6, "Usuń oryginalne pliki HEIC (nieodwracalne)",
                     self.delete_original, danger=True)

        ctk_frame(pad, fg_color=Palette.border, height=1, corner_radius=0).grid(
            row=7, column=0, sticky="ew", pady=9)
        theme.section_title(pad, "Miejsce zapisu").grid(row=8, column=0, sticky="w")

        self.output_switch = ctk_segmented(
            pad, values=["Obok oryginału", "Wybrany folder"],
            command=self._on_output_mode, fg_color=Palette.surface_alt,
            selected_color=Palette.accent, selected_hover_color=Palette.accent_hover,
            unselected_color=Palette.surface_alt,
            unselected_hover_color=Palette.surface_high,
            text_color=Palette.text)
        self.output_switch.set("Obok oryginału")
        self.output_switch.grid(row=9, column=0, sticky="ew", pady=(8, 6))

        folder_row = ctk_frame(pad)
        folder_row.grid(row=10, column=0, sticky="ew")
        folder_row.grid_columnconfigure(0, weight=1)
        self.output_label = ctk_label(folder_row, "—", font=theme.font(11),
                                      text_color=Palette.text_faint, anchor="w")
        self.output_label.grid(row=0, column=0, sticky="ew")
        self.output_button = theme.ghost_button(folder_row, "Zmień", self.pick_output,
                                                width=70, height=28, font=theme.font(11))
        self.output_button.grid(row=0, column=1, sticky="e")
        self.output_button.configure(state="disabled")
        self._refresh_output_label()

    def _switch(self, parent, row: int, text: str, variable, danger: bool = False):
        holder = ctk_frame(parent)
        holder.grid(row=row, column=0, sticky="ew", pady=2)
        holder.grid_columnconfigure(0, weight=1)
        ctk_label(holder, text, font=theme.font(12),
                  text_color=Palette.danger if danger else Palette.text_muted,
                  anchor="w").grid(row=0, column=0, sticky="w")
        switch = ctk_switch(holder, variable=variable, text="",
                            progress_color=Palette.danger if danger else Palette.accent,
                            fg_color=Palette.surface_high,
                            command=self._update_convert_button)
        switch.grid(row=0, column=1, sticky="e")
        return switch

    def _build_actions(self, parent) -> None:
        card = theme.card(parent)
        card.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        card.grid_columnconfigure(0, weight=1)

        pad = ctk_frame(card)
        pad.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        pad.grid_columnconfigure(0, weight=1)

        self.convert_button = theme.primary_button(
            pad, "Konwertuj", self.start_conversion, height=48, font=theme.font(15, "bold"))
        self.convert_button.grid(row=0, column=0, sticky="ew")

        self.progress = ctk_progress(pad, mode="determinate", height=8,
                                     progress_color=Palette.accent,
                                     fg_color=Palette.surface_high)
        self.progress.set(0)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(14, 6))
        self.progress.grid_remove()

        self.progress_label = ctk_label(pad, "", font=theme.font(11),
                                        text_color=Palette.text_muted)
        self.progress_label.grid(row=2, column=0, sticky="w")
        self.progress_label.grid_remove()

        self.open_folder_button = theme.ghost_button(
            pad, "Otwórz folder z wynikiem", self.open_output_folder, height=34,
            font=theme.font(12), compound="left",
            image=theme.icon("folder", 15, Palette.text))
        self.open_folder_button.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.open_folder_button.grid_remove()

        self.cancel_button = theme.ghost_button(
            pad, "Anuluj", self.cancel_conversion, height=32, font=theme.font(12),
            fg_color=Palette.danger_soft, text_color=Palette.danger,
            border_color=Palette.danger)
        self.cancel_button.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.cancel_button.grid_remove()

    def _build_statusbar(self) -> None:
        bar = ctk_frame(self.root)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=theme.PAD,
                 pady=(0, 12))
        bar.grid_columnconfigure(0, weight=1)

        self.status_label = ctk_label(bar, "", font=theme.font(11),
                                      text_color=Palette.text_faint, anchor="w")
        self.status_label.grid(row=0, column=0, sticky="w")

        ctk_label(bar, f"wersja {getattr(self.config, 'APP_VERSION', '')}",
                  font=theme.font(11), text_color=Palette.text_faint,
                  anchor="e").grid(row=0, column=1, sticky="e")

        self._set_status("Gotowy. Dodaj zdjęcia i kliknij „Konwertuj”.")

    # ------------------------------------------------------------------ #
    # helpers for widget construction (keeps customtkinter imports in one place)
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # interactions
    # ------------------------------------------------------------------ #
    def _set_status(self, text: str, colour: str | None = None) -> None:
        self.status_label.configure(text=text,
                                    text_color=colour or Palette.text_faint)

    def _on_quality(self, value) -> None:
        self.quality.set(int(float(value)))
        self.quality_label.configure(text=str(self.quality.get()))

    def _on_output_mode(self, value: str) -> None:
        self.output_mode.set(value)
        chosen = value == "Wybrany folder"
        self.output_button.configure(state="normal" if chosen else "disabled")
        if chosen and not self.custom_output.get():
            self.pick_output()
        self._refresh_output_label()

    def _refresh_output_label(self) -> None:
        if self.output_mode.get() == "Wybrany folder" and self.custom_output.get():
            self.output_label.configure(text=self.custom_output.get(),
                                        text_color=Palette.text)
        else:
            self.output_label.configure(text="Pliki JPG powstaną obok oryginałów",
                                        text_color=Palette.text_faint)

    def pick_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Wybierz zdjęcia HEIC",
            filetypes=[("Zdjęcia HEIC/HEIF", "*.heic *.heif *.HEIC *.HEIF"),
                       ("Wszystkie pliki", "*.*")])
        if paths:
            self.add_paths(list(paths))

    def pick_folder(self) -> None:
        folder = filedialog.askdirectory(title="Wybierz folder ze zdjęciami HEIC")
        if folder:
            self.add_paths([folder])

    def pick_output(self) -> None:
        folder = filedialog.askdirectory(title="Wybierz folder docelowy")
        if folder:
            self.custom_output.set(folder)
            self._refresh_output_label()

    def on_drop(self, event) -> None:
        self._on_drop_leave(event)
        try:
            payload = event.data
        except AttributeError:  # pragma: no cover
            return
        self.add_paths(parse_drop_list(payload))

    def add_paths(self, paths: list[str]) -> None:
        files, warnings = collect_files(paths, recursive=self.recursive.get())
        known = {str(p) for p in self.files}
        added = [f for f in files if str(f) not in known]
        self.files.extend(added)
        self.files.sort(key=lambda p: str(p).lower())
        self.warnings = warnings

        if not added and not warnings:
            self._set_status("Nie znaleziono nowych plików HEIC.", Palette.warning)
        else:
            self._set_status(
                f"Dodano: {theme.files_label(len(added))}."
                + (f" Pominięto: {len(warnings)}." if warnings else ""))

        self._render_rows()
        self._update_convert_button()

    def clear_files(self) -> None:
        self.files.clear()
        self.warnings.clear()
        self.summary = None
        self.last_output_dir = None
        self._render_rows()
        self._update_convert_button()
        self.open_folder_button.grid_remove()
        self._set_status("Lista wyczyszczona.")

    def remove_file(self, path: Path) -> None:
        self.files = [f for f in self.files if f != path]
        self._render_rows()
        self._update_convert_button()

    # ------------------------------------------------------------------ #
    # file rows
    # ------------------------------------------------------------------ #
    def _render_rows(self) -> None:
        for child in self.file_list.winfo_children():
            child.destroy()
        self.rows.clear()

        if not self.files:
            self.files_title.configure(text="Brak plików")
            self.files_subtitle.configure(text="Dodaj zdjęcia, aby rozpocząć")
            self.empty_hint = ctk_label(
                self.file_list,
                "Lista jest pusta.\n\nPrzeciągnij zdjęcia do pola powyżej\n"
                "albo użyj przycisków „Wybierz pliki” / „Wybierz folder”.",
                font=theme.font(12), text_color=Palette.text_faint, justify="center")
            self.empty_hint.grid(row=0, column=0, pady=60)
            return

        total_bytes = sum(self._safe_size(f) for f in self.files)
        self.files_title.configure(text=theme.files_label(len(self.files)))
        self.files_subtitle.configure(text=f"Razem {theme.human_size(total_bytes)}")

        self._visible = self.files[:MAX_VISIBLE_ROWS]
        self._row_index = 0
        self._render_row_batch()

    def _render_row_batch(self) -> None:
        batch = self._visible[self._row_index:self._row_index + ROW_BATCH]
        for offset, path in enumerate(batch):
            self._make_row(self._row_index + offset, path)
        self._row_index += len(batch)

        if self._row_index < len(self._visible):
            self.root.after(1, self._render_row_batch)
        elif len(self.files) > MAX_VISIBLE_ROWS:
            rest = len(self.files) - MAX_VISIBLE_ROWS
            ctk_label(self.file_list, f"… i jeszcze {theme.files_label(rest)}",
                      font=theme.font(11), text_color=Palette.text_faint).grid(
                row=self._row_index + 1, column=0, pady=8)

    def _make_row(self, index: int, path: Path) -> None:
        row = ctk_frame(self.file_list, fg_color="transparent")
        row.grid(row=index, column=0, sticky="ew", pady=1)
        row.grid_columnconfigure(1, weight=1)

        glyph = ctk_label(row, "", image=theme.icon("dot", 11, Palette.text_faint),
                          width=20)
        glyph.grid(row=0, column=0, padx=(6, 2))

        name = ctk_label(row, self._short_name(path), font=theme.font(12),
                         text_color=Palette.text, anchor="w")
        name.grid(row=0, column=1, sticky="ew")

        size = ctk_label(row, theme.human_size(self._safe_size(path)),
                         font=theme.font(11), text_color=Palette.text_faint)
        size.grid(row=0, column=2, padx=8)

        status = ctk_label(row, "", font=theme.font(11), text_color=Palette.text_muted,
                           anchor="e")
        status.grid(row=0, column=3, padx=(0, 6), sticky="e")

        remove = ctk_button(row, "", width=28, height=26, font=theme.font(10),
                            fg_color="transparent", hover_color=Palette.danger_soft,
                            image=theme.icon("close", 12, Palette.text_muted))
        remove.configure(command=lambda p=path: self.remove_file(p))
        # Right padding clears the scrollbar that CTkScrollableFrame overlays.
        remove.grid(row=0, column=4, padx=(0, 16))

        self.rows[str(path)] = {"glyph": glyph, "status": status}

    @staticmethod
    def _status_icon(status: str):
        if status == CONVERTED:
            return theme.icon("check", 12, Palette.success)
        if status == ERROR:
            return theme.icon("close", 12, Palette.danger)
        if status == SKIPPED:
            return theme.icon("dot", 12, Palette.warning)
        return theme.icon("dot", 12, Palette.text_faint)

    @staticmethod
    def _row_status_text(result) -> str:
        """Short, human label for the row.

        The technical error message would stretch the column and read like a
        stack trace; it belongs in the summary dialog instead.
        """
        if result.status == CONVERTED:
            return "usunięto oryginał" if "usunięto" in (result.message or "") else "gotowe"
        if result.status == SKIPPED:
            return "JPG już istnieje"
        if result.status == ERROR:
            return "błąd odczytu"
        return "anulowane"

    @staticmethod
    def _short_name(path: Path, limit: int = 46) -> str:
        name = path.name
        return name if len(name) <= limit else name[:limit - 1] + "…"

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    def _update_convert_button(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        count = len(self.files)
        if count == 0:
            self.convert_button.configure(text="Konwertuj", state="disabled",
                                          fg_color=Palette.surface_high,
                                          text_color=Palette.text_faint,
                                          hover_color=Palette.surface_high)
        else:
            self.convert_button.configure(
                text=f"Konwertuj {theme.files_label(count)}", state="normal",
                fg_color=Palette.accent, text_color="#ffffff",
                hover_color=Palette.accent_hover)

    # ------------------------------------------------------------------ #
    # conversion
    # ------------------------------------------------------------------ #
    def _options(self) -> Options:
        output_dir = None
        if self.output_mode.get() == "Wybrany folder" and self.custom_output.get():
            output_dir = Path(self.custom_output.get())
        return Options(
            quality=self.quality.get(),
            keep_exif=self.keep_exif.get(),
            overwrite=self.overwrite.get(),
            delete_original=self.delete_original.get(),
            recursive=self.recursive.get(),
            output_dir=output_dir,
        )

    def start_conversion(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            return
        if not self.files:
            dialogs.show_message(self.root, "Brak plików",
                                 "Dodaj zdjęcia HEIC, aby rozpocząć konwersję.",
                                 "warning")
            return

        if self.delete_original.get():
            confirmed = dialogs.ask_choice(
                self.root, "Usunąć oryginały?",
                "Opcja „Usuń oryginalne pliki HEIC” jest włączona. "
                "Oryginały zostaną skasowane po udanej konwersji i nie da się "
                "ich przywrócić.\n\nKontynuować?",
                [("Wróć", "back"), ("Tak, usuwaj", "yes")], kind="warning")
            if confirmed != "yes":
                return

        options = self._options()
        if options.output_dir is not None:
            try:
                options.output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                dialogs.show_message(self.root, "Nie mogę użyć folderu",
                                     f"Nie udało się utworzyć katalogu:\n{exc}", "error")
                return

        self.cancel_event.clear()
        self.summary = None
        for entry in self.rows.values():
            entry["glyph"].configure(image=theme.icon("dot", 11, Palette.text_faint))
            entry["status"].configure(text="", text_color=Palette.text_muted)

        self.progress.set(0)
        self.progress.grid()
        self.progress_label.configure(text="Przygotowanie…")
        self.progress_label.grid()
        self.cancel_button.grid()
        self.open_folder_button.grid_remove()
        self.convert_button.configure(state="disabled", text="Konwertuję…")
        self.summary_big.configure(text="—", text_color=Palette.text_muted)
        self.summary_lines.configure(text="Konwersja w toku…")
        self._set_status("Konwersja w toku…")

        files = list(self.files)
        self.worker = threading.Thread(
            target=self._worker, args=(files, options), daemon=True)
        self.worker.start()

    def _worker(self, files, options: Options) -> None:
        def on_progress(index, total, result) -> None:
            self.events.put(("progress", index, total, result))

        try:
            summary = convert_files(files, options, on_progress=on_progress,
                                    should_cancel=self.cancel_event.is_set)
            self.events.put(("done", summary))
        except Exception as exc:  # noqa: BLE001 - never let the thread die silently
            self.events.put(("fatal", f"{type(exc).__name__}: {exc}"))

    def _pump_events(self) -> None:
        """Drain the worker queue on the UI thread.

        Every handler is wrapped: an exception escaping a Tk `after` callback
        aborts the chain, which silently freezes the progress bar forever
        instead of surfacing the error.
        """
        try:
            while True:
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                kind = event[0]
                try:
                    if kind == "progress":
                        self._on_file_done(*event[1:])
                    elif kind == "done":
                        self._on_conversion_done(event[1])
                    elif kind == "fatal":
                        self._on_fatal(event[1])
                except Exception as exc:  # noqa: BLE001
                    self._on_fatal(f"blad obslugi zdarzenia ({kind}): {exc}")
        finally:
            if not self._closing:
                self._pump_id = self.root.after(80, self._pump_events)

    def _base_title(self) -> str:
        """Window title - the full name with the author, as set in config.py."""
        return getattr(self.config, "APP_TITLE", "HEIC --> JPG Converter")

    def _on_file_done(self, index: int, total: int, result) -> None:
        entry = self.rows.get(str(result.source))
        if entry:
            colour = theme.status_colour(result.status)
            entry["glyph"].configure(image=self._status_icon(result.status))
            entry["status"].configure(text=self._row_status_text(result),
                                      text_color=colour)

        self.progress.set(index / total if total else 0)
        percent = int(100 * index / total) if total else 0
        self.progress_label.configure(
            text=f"{index} / {total}  ({percent}%)   {self._short_name(result.source, 30)}")
        self.root.title(f"{self._base_title()} — {percent}%")

    def _on_conversion_done(self, summary: Summary) -> None:
        self.summary = summary
        self.worker = None
        self.cancel_button.grid_remove()
        self.progress.grid_remove()
        self.progress_label.grid_remove()
        self.root.title(self._base_title())
        self._update_convert_button()

        options = self._options()
        if options.output_dir is not None:
            self.last_output_dir = options.output_dir
        elif self.files:
            self.last_output_dir = self.files[0].parent

        if summary.converted and self.last_output_dir:
            self.open_folder_button.grid()

        self._refresh_summary_card(summary)

        parts = [f"Skonwertowano: {summary.converted}"]
        if summary.skipped:
            parts.append(f"pominięto: {summary.skipped}")
        if summary.errors:
            parts.append(f"błędy: {summary.errors}")
        if summary.cancelled:
            parts.append(f"anulowano: {summary.cancelled}")
        self._set_status(" · ".join(parts)
                         + f" · {summary.seconds:.1f} s".replace(".", ","),
                         Palette.success if not summary.errors else Palette.warning)

        message = self._summary_text(summary)
        if summary.cancelled:
            kind = "warning"
        elif summary.errors:
            kind = "warning"
        else:
            kind = "success"
        dialogs.show_message(self.root, "Konwersja zakończona", message, kind)

        # Count the work, then reconsider asking for support. Deferred by a
        # moment so the request never lands on top of the result window, and
        # never before the user has seen what they got.
        support.register_conversion(self.values, summary.converted)
        self.root.after(400, self.maybe_ask_for_support)

        if self.delete_original.get() and summary.converted:
            for path in [r.source for r in summary.results if r.status == CONVERTED]:
                if path.exists():
                    continue
            self._render_rows()

    def _refresh_summary_card(self, summary: Summary) -> None:
        colour = Palette.success if not summary.errors else Palette.warning
        self.summary_big.configure(text=theme.files_label(summary.converted),
                                   text_color=colour)
        lines = []
        if summary.saved_bytes:
            lines.append(f"Zaoszczędzono {theme.human_size(summary.saved_bytes)}")
        else:
            lines.append(f"Rozmiar wyniku: {theme.human_size(summary.bytes_after)}")
        if summary.errors or summary.skipped:
            lines.append(f"Pominięte/błędy: {summary.skipped + summary.errors}")
        lines.append(f"Czas: {summary.seconds:.1f} s".replace(".", ","))
        self.summary_lines.configure(text="\n".join(lines))

    def _summary_text(self, summary: Summary) -> str:
        lines = [
            f"Przetworzono plików: {summary.total}",
            f"  • skonwertowano: {summary.converted}",
        ]
        if summary.skipped:
            lines.append(f"  • pominięto (plik JPG już istniał): {summary.skipped}")
        if summary.errors:
            lines.append(f"  • błędy: {summary.errors}")
        if summary.cancelled:
            lines.append(f"  • anulowane: {summary.cancelled}")
        lines.append("")
        lines.append(f"Rozmiar przed: {theme.human_size(summary.bytes_before)}")
        lines.append(f"Rozmiar po:    {theme.human_size(summary.bytes_after)}")
        seconds = f"{summary.seconds:.1f}".replace(".", ",")
        speed = f"  ({summary.speed:.1f} plików/s)".replace(".", ",") if summary.speed else ""
        lines.append(f"Czas: {seconds} s{speed}")
        if summary.errors:
            lines.append("")
            lines.append("Pliki z błędem:")
            for result in summary.results:
                if result.status == ERROR:
                    lines.append(f"  – {result.source.name}: {result.message}")
        return "\n".join(lines)

    def _on_fatal(self, message: str) -> None:
        # Kept for diagnostics: the UI shows a dialog, but a frozen-looking
        # progress bar in the field is best explained by this string.
        self.last_error = message
        self.worker = None
        self.cancel_button.grid_remove()
        self.progress.grid_remove()
        self.progress_label.grid_remove()
        self._update_convert_button()
        self._set_status("Konwersja przerwana.", Palette.danger)
        dialogs.show_message(self.root, "Błąd konwersji",
                             f"Wystąpił nieoczekiwany błąd:\n{message}", "error")

    def cancel_conversion(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.cancel_event.set()
            self._set_status("Anulowanie…", Palette.warning)
            self.cancel_button.configure(state="disabled")

    def open_output_folder(self) -> None:
        folder = self.last_output_dir
        if not folder or not Path(folder).exists():
            dialogs.show_message(self.root, "Folder niedostępny",
                                 "Nie mogę znaleźć folderu z wynikiem.", "warning")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(folder))  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:  # pragma: no cover
            dialogs.show_message(self.root, "Nie mogę otworzyć folderu", str(exc), "error")

    # ------------------------------------------------------------------ #
    # help, support and information windows
    # ------------------------------------------------------------------ #
    def open_support(self) -> None:
        support.open_manual_support(self.root, self.config)

    def open_about(self) -> None:
        about.show_about(self.root, self.config, self.values)

    def open_licence(self) -> None:
        about.show_licence(self.root)

    def open_notices(self) -> None:
        about.show_third_party(self.root, self.config)

    def open_privacy(self) -> None:
        about.show_privacy(self.root, self.config, self.values)

    def write_to_author(self) -> None:
        about.ask_message(self.root, self.config, self.values)

    def open_help_menu(self) -> None:
        """Native popup menu under the Help button.

        A menu keeps the header tidy while leaving every window one click away;
        a pile of buttons would crowd out the actual work.
        """
        menu = tkinter.Menu(self.root, tearoff=0)
        menu.add_command(label="\u2615  Postaw kawę", command=self.open_support)
        menu.add_separator()
        menu.add_command(label="O programie", command=self.open_about)
        menu.add_command(label="Licencja", command=self.open_licence)
        menu.add_command(label="Biblioteki użyte w programie", command=self.open_notices)
        menu.add_command(label="Prywatność i statystyki", command=self.open_privacy)
        menu.add_separator()
        menu.add_command(label="Napisz do mnie", command=self.write_to_author)

        anchor = self.help_button or self.root
        try:
            x = anchor.winfo_rootx()
            y = anchor.winfo_rooty() + anchor.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def maybe_ask_for_support(self) -> None:
        """Ask for a donation - only when support.py says the time is right.

        Called after a finished conversion, never during one, and never in a
        way that blocks the next task.
        """
        try:
            support.maybe_ask(self.root, self.values, self.config)
        except Exception:  # noqa: BLE001 - asking for money must never break work
            pass

    # ------------------------------------------------------------------ #
    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            confirmed = dialogs.ask_choice(
                self.root, "Konwersja trwa",
                "Trwa konwersja. Zamknąć program mimo to?",
                [("Zostań", "stay"), ("Zamknij", "close")], kind="warning")
            if confirmed != "close":
                return
            self.cancel_event.set()
        # Stop the polling chain before tearing the interpreter down, otherwise
        # a pending `after` callback fires into a dead window and prints
        # 'invalid command name ..._pump_events' on the console.
        self._closing = True
        if self._pump_id is not None:
            try:
                self.root.after_cancel(self._pump_id)
            except Exception:
                pass
            self._pump_id = None
        self.root.destroy()


# --------------------------------------------------------------------------- #
# thin wrappers so customtkinter is imported in one place
# --------------------------------------------------------------------------- #
def _ctk():
    import customtkinter as ctk

    return ctk


def ctk_frame(master, **kwargs):
    ctk = _ctk()
    options = {"fg_color": "transparent"}
    options.update(kwargs)
    return ctk.CTkFrame(master, **options)


def ctk_label(master, text: str = "", **kwargs):
    ctk = _ctk()
    options = {"text": text}
    options.update(kwargs)
    return ctk.CTkLabel(master, **options)


def ctk_button(master, text: str = "", **kwargs):
    ctk = _ctk()
    options = {"text": text}
    options.update(kwargs)
    return ctk.CTkButton(master, **options)


def ctk_switch(master, **kwargs):
    return _ctk().CTkSwitch(master, **kwargs)


def ctk_slider(master, **kwargs):
    return _ctk().CTkSlider(master, **kwargs)


def ctk_progress(master, **kwargs):
    return _ctk().CTkProgressBar(master, **kwargs)


def ctk_segmented(master, **kwargs):
    return _ctk().CTkSegmentedButton(master, **kwargs)


def ctk_scrollable(master, **kwargs):
    return _ctk().CTkScrollableFrame(master, **kwargs)
