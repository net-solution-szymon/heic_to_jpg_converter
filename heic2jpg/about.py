"""Information windows: about, licence, third-party notices, privacy, contact.

Two obligations are met here rather than buried in a README:

  * the licence and the notices of the bundled libraries are readable from
    inside the program (LGPL requires the notices to travel with the program);
  * what the program reports about the user, and how to switch it off, is
    stated in plain Polish before any of it is sent.
"""
from __future__ import annotations

import sys
from pathlib import Path

import customtkinter as ctk

from . import dialogs, support, telemetry, theme
from .theme import Palette

MAX_MESSAGE_LENGTH = 2000
MAX_CONTACT_LENGTH = 120


# --------------------------------------------------------------------------- #
# files shipped next to the program
# --------------------------------------------------------------------------- #
def resource_dir() -> Path:
    """Where the data files live, both from source and from a PyInstaller build."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parent.parent


def legal_text(filename: str) -> str:
    """Read a file from legal/. Returns a readable note if it is missing."""
    path = resource_dir() / "legal" / filename
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return (f"Nie mogę odczytać pliku {filename}.\n\n"
                f"Szukany pod adresem: {path}\nBłąd: {exc}")


# --------------------------------------------------------------------------- #
# about
# --------------------------------------------------------------------------- #
def about_text(config, values) -> str:
    lines = [
        getattr(config, "APP_NAME", "HEIC \u2192 JPG Converter"),
        f"Wersja {getattr(config, 'APP_VERSION', '?')}",
        "",
        "Darmowy konwerter zdjęć HEIC (iPhone) na JPG. Bez limitów, bez opłat, "
        "bez rejestracji.",
        "",
        "Program zbiera anonimowe statystyki: losowy identyfikator instalacji, "
        "wersję programu, system i liczbę przekonwertowanych plików. Nie zbiera "
        "nazw plików, ścieżek ani danych o sprzęcie. Szczegóły znajdziesz "
        "w oknie „Prywatność”, gdzie można to wyłączyć.",
        "",
        support.thank_again_text(config),
        "",
        f"Konwersji w tym programie: {int(values.get('converted_total', 0))}",
        f"Uruchomień: {int(values.get('sessions', 0))}",
    ]
    if getattr(config, "SUPPORT_EMAIL", ""):
        lines += ["", f"Kontakt: {config.SUPPORT_EMAIL}"]
    if getattr(config, "GITHUB_URL", ""):
        lines += ["", f"Kod źródłowy: {config.GITHUB_URL}"]
    return "\n".join(lines)


def first_run_notice(master, config, values) -> None:
    """Tell the user what is reported, once, before anything is reported.

    Sending statistics without ever saying so would be the wrong way round;
    this dialog is the "saying so". It also offers the off switch right there,
    so the honest choice is also the easy one.
    """
    answer = dialogs.ask_choice(
        master,
        "Zanim zaczniesz",
        "Program jest darmowy i zbiera anonimowe statystyki: losowy "
        "identyfikator instalacji, wersję programu, system i liczbę "
        "przekonwertowanych plików.\n\n"
        "Nie zbiera nazw ani zawartości zdjęć, ścieżek, Twojego imienia ani "
        "żadnych informacji o sprzęcie.\n\n"
        "Możesz to wyłączyć teraz albo później w menu Pomoc → Prywatność.",
        [("Rozumiem, włącz", "on"), ("Wyłącz statystyki", "off")],
        kind="info",
    )
    if answer == "off":
        telemetry.set_enabled(values, False)


def show_about(master, config, values) -> None:
    buttons = [("Zamknij", "close", "primary")]
    if support.support_url(config):
        buttons.insert(0, ("\u2615 Postaw kawę", "support", "ghost"))
    answer = dialogs.show_text(master, "O programie", about_text(config, values),
                               width=640, height=520, buttons=buttons)
    if answer == "support":
        support.open_manual_support(master, config)


# --------------------------------------------------------------------------- #
# licence and notices
# --------------------------------------------------------------------------- #
def licence_text() -> str:
    """Tresc umowy licencyjnej pokazywana uzytkownikowi.

    Umowa ma wpisane dane autora, adres repozytorium i adres kontaktowy, wiec
    nie ma tu nic do podstawiania - zwracamy plik w takiej postaci, w jakiej
    lezy w katalogu legal/.

    Wczesniej funkcja podstawiala wartosci z config.py w miejsce nawiasow
    [ADRES REPOZYTORIUM] i [ADRES WSPARCIA]. Po uzupelnieniu umowy te nawiasy
    zniknely, wiec podstawianie bylo martwym kodem. Brak nawiasow pilnuje test.
    """
    return legal_text("EULA-HEIC-to-JPG-Converter.txt")


def show_licence(master) -> None:
    dialogs.show_text(master, "Licencja", licence_text(), width=820, height=640)


def show_third_party(master, config) -> None:
    dialogs.show_text(master, "Biblioteki użyte w programie",
                      legal_text("THIRD-PARTY-NOTICES.txt"),
                      width=820, height=640)


# --------------------------------------------------------------------------- #
# privacy
# --------------------------------------------------------------------------- #
def privacy_text(config, values) -> str:
    state = "WŁĄCZONE" if telemetry.enabled(values) else "WYŁĄCZONE"
    return (
        "Co program wysyła\n"
        "----------------\n"
        "  - losowy identyfikator instalacji (nadany przy pierwszym uruchomieniu)\n"
        "  - wersję programu\n"
        "  - nazwę i wersję systemu\n"
        "  - łączną liczbę przekonwertowanych plików\n\n"
        "Czego program NIE wysyła\n"
        "------------------------\n"
        "  - nazw ani zawartości zdjęć\n"
        "  - ścieżek do folderów\n"
        "  - nazwy użytkownika ani nazwy komputera\n"
        "  - żadnego identyfikatora sprzętu (numer dysku, adres MAC, UUID płyty)\n\n"
        "Po co to jest\n"
        "-------------\n"
        "Żeby wiedzieć, ile osób używa programu i czy warto go dalej rozwijać. "
        "To zwykły licznik - nie da się z niego ustalić, kim jesteś.\n\n"
        "Jak długo\n"
        "---------\n"
        "Dane trzymane są na serwerze prowadzonym przez autora programu i służą "
        "wyłącznie do statystyk. Adresy IP nie są zapisywane.\n\n"
        "Twoja decyzja\n"
        "-------------\n"
        "Możesz to wyłączyć w każdej chwili. Po wyłączeniu program nie łączy się "
        "z serwerem ani razu. Usunięcie pliku danych programu kasuje też "
        "identyfikator instalacji.\n\n"
        f"Stan obecny: {state}\n"
        f"Identyfikator instalacji: {values.get('install_id') or '(jeszcze nie nadany)'}\n"
        f"Plik danych: {_data_path()}"
    )


def _data_path() -> str:
    from . import store

    return str(store.data_file())


def show_privacy(master, config, values) -> bool:
    """Privacy notice with a live switch. Returns True when the value changed."""
    window = ctk.CTkToplevel(master)
    window.title("Prywatność")
    window.configure(fg_color=Palette.bg)
    window.minsize(600, 480)

    head = ctk.CTkFrame(window, fg_color="transparent")
    head.pack(fill="x", padx=22, pady=(20, 6))
    ctk.CTkLabel(head, text="", image=theme.icon("info", 20, Palette.accent),
                 width=26).pack(side="left")
    ctk.CTkLabel(head, text="Prywatność i statystyki", font=theme.font(16, "bold"),
                 text_color=Palette.text).pack(side="left", padx=(8, 0))

    box = ctk.CTkTextbox(window, font=theme.font(12), fg_color=Palette.surface,
                         border_color=Palette.border, border_width=1,
                         text_color=Palette.text_muted, wrap="word",
                         corner_radius=theme.RADIUS_SMALL)
    box.pack(fill="both", expand=True, padx=22, pady=(4, 12))
    box.insert("1.0", privacy_text(config, values))
    box.configure(state="disabled")

    switch_var = ctk.BooleanVar(value=telemetry.enabled(values))

    row = ctk.CTkFrame(window, fg_color="transparent")
    row.pack(fill="x", padx=22, pady=(0, 20))

    ctk.CTkSwitch(row, text="Wysyłaj anonimowe statystyki", variable=switch_var,
                  font=theme.font(12), text_color=Palette.text,
                  progress_color=Palette.accent,
                  button_color=Palette.surface_alt).pack(side="left")

    changed = {"value": False}

    def close() -> None:
        window.destroy()

    def confirm() -> None:
        wanted = bool(switch_var.get())
        if wanted != telemetry.enabled(values):
            telemetry.set_enabled(values, wanted)
            changed["value"] = True
        close()

    theme.ghost_button(row, "Zamknij", close).pack(side="right", padx=(8, 0))
    theme.primary_button(row, "Zapisz", confirm).pack(side="right")

    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Escape>", lambda _event: close())
    window.update_idletasks()
    x = (window.winfo_screenwidth() - 760) // 2
    y = (window.winfo_screenheight() - 560) // 3
    window.geometry(f"760x560+{max(0, x)}+{max(0, y)}")
    try:
        window.grab_set()
        window.focus_force()
    except Exception:  # pragma: no cover
        pass
    master.wait_window(window)
    return changed["value"]


# --------------------------------------------------------------------------- #
# contact form
# --------------------------------------------------------------------------- #
def ask_message(master, config, values) -> bool:
    """The "napisz do mnie" form. Returns True when a message was sent.

    The consent checkbox is required rather than decorative: the message - and
    especially an e-mail address - is personal data, and it may only be handled
    with the sender's knowledge.
    """
    window = ctk.CTkToplevel(master)
    window.title("Napisz do mnie")
    window.configure(fg_color=Palette.bg)
    window.minsize(560, 560)

    body = ctk.CTkFrame(window, fg_color="transparent")
    body.pack(fill="both", expand=True, padx=22, pady=(20, 12))

    ctk.CTkLabel(body, text="", image=theme.icon("info", 20, Palette.accent),
                 width=26).grid(row=0, column=0, sticky="nw", pady=(2, 0))
    ctk.CTkLabel(body, text="Napisz do mnie", font=theme.font(16, "bold"),
                 text_color=Palette.text).grid(row=0, column=1, sticky="w", padx=(8, 0))

    ctk.CTkLabel(body, text="Pomysł, błąd, pytanie - wszystko jest mile widziane. "
                            "Odpowiem, jeśli podasz kontakt.",
                 font=theme.font(12), text_color=Palette.text_muted,
                 justify="left", anchor="w", wraplength=470).grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(8, 14))

    message_box = ctk.CTkTextbox(body, font=theme.font(13), fg_color=Palette.surface,
                                 border_color=Palette.border, border_width=1,
                                 text_color=Palette.text, wrap="word", height=170,
                                 corner_radius=theme.RADIUS_SMALL)
    message_box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 10))

    contact_entry = ctk.CTkEntry(body, height=38, font=theme.font(13),
                                 fg_color=Palette.surface_alt,
                                 border_color=Palette.border, text_color=Palette.text,
                                 placeholder_text="Twój e-mail (opcjonalnie)",
                                 corner_radius=theme.RADIUS_SMALL)
    contact_entry.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 12))

    diagnostics_var = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(body, text="Dołącz informacje o programie (wersja, system)",
                    variable=diagnostics_var, font=theme.font(12),
                    text_color=Palette.text_muted, fg_color=Palette.accent,
                    hover_color=Palette.accent_hover,
                    border_color=Palette.border).grid(row=4, column=0, columnspan=2,
                                                      sticky="w", pady=(0, 8))

    consent_var = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(
        body,
        text="Zgadzam się na przetwarzanie mojej wiadomości i adresu e-mail\n"
             "wyłącznie w celu odpowiedzi na nią.",
        variable=consent_var, font=theme.font(12), text_color=Palette.text_muted,
        fg_color=Palette.accent, hover_color=Palette.accent_hover,
        border_color=Palette.border).grid(row=5, column=0, columnspan=2,
                                          sticky="w", pady=(0, 6))

    body.grid_columnconfigure(1, weight=1)

    status = ctk.CTkLabel(body, text="", font=theme.font(11),
                          text_color=Palette.danger, anchor="w", justify="left",
                          wraplength=470)
    status.grid(row=6, column=0, columnspan=2, sticky="w", pady=(6, 0))

    sent = {"value": False}

    def send() -> None:
        text = message_box.get("1.0", "end").strip()
        contact = contact_entry.get().strip()

        if len(text) < 5:
            status.configure(text="Napisz coś więcej - przynajmniej kilka słów.")
            return
        if len(text) > MAX_MESSAGE_LENGTH:
            status.configure(text=f"Wiadomość jest za długa "
                                  f"({len(text)} z {MAX_MESSAGE_LENGTH} znaków).")
            return
        if len(contact) > MAX_CONTACT_LENGTH:
            status.configure(text="Adres kontaktowy jest za długi.")
            return
        if not consent_var.get():
            status.configure(text="Zaznacz zgodę - bez niej nie mogę przyjąć "
                                  "wiadomości.")
            return

        status.configure(text="Wysyłam...", text_color=Palette.text_muted)
        window.update_idletasks()

        ok, error = telemetry.send_message(
            values, config, text, contact, bool(diagnostics_var.get()))
        if ok:
            sent["value"] = True
            window.destroy()
            return
        # Komunikat jest juz napisany po ludzku (telemetry._human_reason),
        # wiec nie dokladamy wlasnego "sprawdz internet" - powtarzalby sie
        # albo klocil z nim.
        status.configure(text=f"Nie udało się wysłać.\n{error}",
                         text_color=Palette.danger)

    row = ctk.CTkFrame(window, fg_color="transparent")
    row.pack(fill="x", padx=22, pady=(0, 20))
    theme.ghost_button(row, "Anuluj", window.destroy).pack(side="right", padx=(8, 0))
    theme.primary_button(row, "Wyślij", send).pack(side="right")

    window.protocol("WM_DELETE_WINDOW", window.destroy)
    window.bind("<Escape>", lambda _event: window.destroy())
    message_box.focus_set()

    window.update_idletasks()
    x = (window.winfo_screenwidth() - 640) // 2
    y = (window.winfo_screenheight() - 620) // 3
    window.geometry(f"640x620+{max(0, x)}+{max(0, y)}")
    try:
        window.grab_set()
        window.focus_force()
    except Exception:  # pragma: no cover
        pass

    master.wait_window(window)
    if sent["value"]:
        dialogs.show_message(master, "Dziękuję!", "Wiadomość wysłana.", "success")
    return sent["value"]
