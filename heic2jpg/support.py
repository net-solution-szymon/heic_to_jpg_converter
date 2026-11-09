"""Asking for support - and the rules that keep it from becoming nagware.

A prompt that shows up too often, or too early, costs more users than the
money it raises. So the rules are deliberately conservative and the user's
answer is always remembered:

  * the first prompt appears only after PROMPT_AFTER_FILES files have been
    converted - i.e. once the program has demonstrably been useful;
  * at most one prompt every PROMPT_COOLDOWN_DAYS;
  * the next threshold only after another PROMPT_AFTER_FILES files;
  * "nie pokazuj wiecej" and "juz wsparlem" are permanent and always honoured;
  * closing the window just snoozes it - it does not silence the program
    forever, because a mis-click should not be irreversible.

The prompt NEVER blocks anything: it is an ordinary dialog with a way out.
The program is fully functional whether or not anybody ever pays.
"""
from __future__ import annotations

import webbrowser
from datetime import datetime, timezone

from . import dialogs, store, theme
from .theme import Palette

# Dialog result values.
CHOICE_SUPPORT = "support"
CHOICE_DONATED = "donated"
CHOICE_NEVER = "never"
CHOICE_LATER = "later"

# Przyciski prosby o wsparcie, w kolejnosci od najwazniejszego.
# Ostatnia pozycja to ta, ktora zwraca zamkniecie okna (Escape) - dlatego na
# koncu jest lagodne "Nie teraz", a nie trwale wyciszenie programu.
# Krotkie etykiety i szerokie okno sa konieczne, zeby CZTERY przyciski
# zmiescily sie w jednym rzedzie: przy domyslnej szerokosci ostatni wychodzil
# poza krawedz i uzytkownik go nie widzial.
PROMPT_TITLE = "Podoba Ci się program?"
# Zmierzone: sama tresc (cztery przyciski + marginesy) potrzebuje ok. 642 px.
# Wartosc jest z zapasem, a test test_support_prompt_fits_all_four_buttons
# pilnuje, zeby po zmianie etykiet znow nie ucielo ostatniego przycisku.
PROMPT_WIDTH = 660
PROMPT_BUTTONS = [
    ("\u2615 Wspieram", CHOICE_SUPPORT),
    ("Już wsparłem", CHOICE_DONATED),
    ("Nie pokazuj więcej", CHOICE_NEVER),
    ("Nie teraz", CHOICE_LATER),
]


# --------------------------------------------------------------------------- #
# counters
# --------------------------------------------------------------------------- #
def start_session(values: dict) -> dict:
    """Count this run. Called once at startup."""
    return store.bump(values, store.KEY_SESSIONS, 1)


def register_conversion(values: dict, converted: int) -> dict:
    """Add a finished run to the lifetime counter."""
    if converted <= 0:
        return values
    return store.bump(values, store.KEY_CONVERTED_TOTAL, int(converted))


def converted_total(values: dict) -> int:
    return int(values.get(store.KEY_CONVERTED_TOTAL, 0))


# --------------------------------------------------------------------------- #
# should we ask?
# --------------------------------------------------------------------------- #
def _days_since_last_prompt(values: dict) -> float | None:
    last = values.get(store.KEY_LAST_PROMPT_AT) or ""
    if not last:
        return None
    try:
        previous = datetime.fromisoformat(last)
    except ValueError:
        return None
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - previous).total_seconds() / 86400


def should_ask(values: dict, config) -> bool:
    """True when the user has earned a (polite, single) request for support."""
    if values.get(store.KEY_NEVER_PROMPT):
        return False

    step = int(getattr(config, "PROMPT_AFTER_FILES", 50) or 50)
    shown = int(values.get(store.KEY_PROMPT_COUNT, 0))
    if converted_total(values) < step * (shown + 1):
        return False

    cooldown = float(getattr(config, "PROMPT_COOLDOWN_DAYS", 30) or 0)
    days = _days_since_last_prompt(values)
    if days is not None and days < cooldown:
        return False
    return True


# --------------------------------------------------------------------------- #
# the prompt itself
# --------------------------------------------------------------------------- #
def prompt_text(values: dict, config) -> str:
    total = converted_total(values)
    # Odmiana przez `plural`, nie reczne "plikow": przy 53 plikach poprawna
    # forma to "pliki", a nie "plikow" - literowka w oknie z prosba o pieniadze
    # wyglada szczegolnie zle.
    files = theme.plural(total, "plik", "pliki", "plików")
    return (
        f"Konwertujesz ze mną zdjęcia bez limitów i bez opłat - to już "
        f"{total} {files}.\n\n"
        "Program jest darmowy i taki pozostanie. Jeśli się przydaje i chcesz "
        "wesprzeć jego rozwój, możesz postawić mi kawę. To dobrowolne i nic "
        "nie zmienia w działaniu programu - ale bardzo pomaga."
    )


def ask_for_support(master, values: dict, config) -> str:
    """Show the support prompt and remember the answer. Returns the choice."""
    answer = dialogs.ask_choice(
        master,
        PROMPT_TITLE,
        prompt_text(values, config),
        PROMPT_BUTTONS,
        kind="info",
        width=PROMPT_WIDTH,
    )

    # Count it as shown regardless of the answer, so "nie teraz" still starts
    # the cooldown - otherwise the next conversion would ask again straight away.
    store.bump(values, store.KEY_PROMPT_COUNT, 1)
    store.set_value(values, store.KEY_LAST_PROMPT_AT, datetime.now(timezone.utc)
                    .replace(microsecond=0).isoformat())

    if answer == CHOICE_SUPPORT:
        open_support_page(config)
    elif answer == CHOICE_DONATED:
        store.set_value(values, store.KEY_NEVER_PROMPT, True)
        dialogs.show_message(
            master, "Dziękuję!",
            "Dziękuję za wsparcie - to naprawdę wiele dla mnie znaczy.\n\n"
            "Nie będę już o tym przypominał.", "success")
    elif answer == CHOICE_NEVER:
        store.set_value(values, store.KEY_NEVER_PROMPT, True)
        dialogs.show_message(
            master, "Jasne",
            "Rozumiem i szanuję. Nie będę więcej pytał.\n\n"
            "Program działa dalej tak samo - bez ograniczeń.", "info")

    return answer


def maybe_ask(master, values: dict, config) -> bool:
    """Show the prompt if it is due. Returns True when it was shown."""
    if not should_ask(values, config):
        return False
    ask_for_support(master, values, config)
    return True


# --------------------------------------------------------------------------- #
# opening the page
# --------------------------------------------------------------------------- #
def support_url(config) -> str:
    return (getattr(config, "SUPPORT_URL", "") or "").strip()


def open_support_page(config) -> bool:
    """Open the donation page in the user's browser.

    We never handle payments ourselves - the browser does it, on the
    platform's own secure page.
    """
    url = support_url(config)
    if not url:
        return False
    try:
        return webbrowser.open(url)
    except Exception:  # pragma: no cover - no browser configured
        return False


def open_manual_support(master, config) -> None:
    """The "Postaw kawę" menu item: open the page, or explain how to set it up."""
    if open_support_page(config):
        return
    dialogs.show_message(
        master, "Adres wsparcia nie jest ustawiony",
        "Uzupełnij SUPPORT_URL w pliku config.py, na przykład:\n\n"
        "    SUPPORT_URL = \"https://buycoffee.to/twojanazwa\"\n\n"
        "Polecenie otwiera stronę w przeglądarce - program sam nigdy nie "
        "obsługuje płatności.",
        "warning")


def thank_again_text(config) -> str:
    """Small line used under the About window."""
    total = support_url(config)
    if not total:
        return ("Program jest darmowy. Aby dodać przycisk wsparcia, uzupełnij "
                "SUPPORT_URL w pliku config.py.")
    return "Jeśli program się przydaje, możesz postawić mi kawę."


# Kept so the palette stays importable from here in tests that check colours.
WARNING_COLOUR = Palette.warning
