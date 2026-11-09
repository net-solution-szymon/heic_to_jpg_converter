"""Testy okna: budowa interfejsu i prawdziwa konwersja przez GUI.

Wymagaja wyswietlacza. Na maszynie bez pulpitu uruchamiaj:

    xvfb-run -a python -m pytest

Lapia to, czego testy silnika nie widza: opcje widzetow, ktorych nie ma,
bledy Tcl, petle zdarzen, ktora nigdy nie dojrzewa.
"""
import time

import pytest

pytest.importorskip("customtkinter")
pytest.importorskip("tkinterdnd2")

from heic2jpg import about, dialogs, store, theme  # noqa: E402
from heic2jpg.app import ConverterApp  # noqa: E402
from heic2jpg.window import AppWindow  # noqa: E402


def _display_available() -> bool:
    try:
        root = AppWindow()
    except Exception:
        return False
    root.destroy()
    return True


pytestmark = pytest.mark.skipif(not _display_available(),
                                reason="brak wyswietlacza X (uzyj xvfb-run)")


class _Config:
    """Minimalny obiekt konfiguracji - testy nie czytaja prawdziwego config.py."""

    APP_NAME = "HEIC \u2192 JPG Converter"
    APP_TITLE = "HEIC --> JPG Converter by Szymon Jankojć"
    APP_VERSION = "1.0.0-test"
    SERVER_URL = ""
    SUPPORT_URL = "https://buycoffee.to/test"
    SUPPORT_EMAIL = ""
    GITHUB_URL = "https://github.com/przyklad/test"
    PROMPT_AFTER_FILES = 50
    PROMPT_COOLDOWN_DAYS = 30
    TELEMETRY_TIMEOUT = 1
    TELEMETRY_INTERVAL_HOURS = 24
    TELEMETRY_ENABLED_BY_DEFAULT = True


@pytest.fixture
def values(isolated_data):
    return store.load()


@pytest.fixture
def app(monkeypatch, values):
    """Prawdziwe okno programu z wylaczonymi oknami modalnymi."""
    theme.apply_appearance()
    # Testy nie moga czekac na klikniecie czlowieka.
    monkeypatch.setattr(dialogs, "show_message", lambda *a, **k: None)
    monkeypatch.setattr(dialogs, "ask_choice", lambda *a, **k: "later")

    root = AppWindow()
    root.withdraw()
    converter = ConverterApp(root, _Config, values)
    yield converter

    # Najpierw zatrzymujemy petle, potem niszczymy okno - inaczej zalegly
    # callback `after` strzela w martwe okno i drukuje blad Tcl.
    converter._closing = True
    if converter._pump_id is not None:
        try:
            root.after_cancel(converter._pump_id)
        except Exception:
            pass
    try:
        root.destroy()
    except Exception:
        pass


def pump(app, seconds: float = 5.0) -> None:
    """Kreci petla zdarzen do momentu, gdy konwersja sie skonczy."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.root.update()
        time.sleep(0.02)
        if app.summary is not None:
            app.root.update()
            return
    raise AssertionError(
        f"konwersja nie zakonczyla sie (blad: {app.last_error!r}, "
        f"status: {app.status_label.cget('text')!r})")


# --------------------------------------------------------------------------- #
# budowa okna
# --------------------------------------------------------------------------- #
def test_window_builds_with_all_sections(app):
    assert app.root.title() == _Config.APP_TITLE
    assert app.convert_button.cget("text") == "Konwertuj"
    assert str(app.convert_button.cget("state")) == "disabled"
    assert app.summary_big.cget("text") == "\u2014"


def test_support_and_help_buttons_are_present(app):
    """Wsparcie musi byc widoczne od razu, a nie schowane w menu."""
    assert "\u2615" in app.support_button.cget("text")
    assert app.help_button.cget("text") == "Pomoc"


def test_no_licence_controls_remain(app):
    """Po przejsciu na darowizny nie moze zostac zaden slad po licencji."""
    labels = []

    def walk(widget):
        try:
            text = widget.cget("text")
            if text:
                labels.append(str(text))
        except Exception:
            pass
        for child in widget.winfo_children():
            walk(child)

    walk(app.root)
    joined = " ".join(labels).lower()
    for word in ("licencja licencyjny", "przedłuż licencję", "trial",
                 "klucz licencyjny", "tryb deweloperski"):
        assert word not in joined, f"w oknie zostal element licencyjny: {word}"


def test_support_prompt_fits_all_four_buttons(values):
    """Cztery przyciski musza zmiescic sie w oknie.

    Regresja: przy domyslnej szerokosci okna czwarty przycisk ("Nie teraz")
    wychodzil poza krawedz - byl w interfejsie, ale uzytkownik go nie widzial,
    wiec nie mial jak spokojnie odmowic.
    """
    from heic2jpg import support
    from heic2jpg.dialogs import ModalDialog

    root = AppWindow()
    root.withdraw()
    dialog = None
    try:
        buttons = [(label, value, "primary" if index == 0 else "ghost")
                   for index, (label, value) in enumerate(support.PROMPT_BUTTONS)]
        dialog = ModalDialog(root, support.PROMPT_TITLE,
                             support.prompt_text(values, _Config),
                             buttons, kind="info", width=support.PROMPT_WIDTH)
        dialog.update_idletasks()

        needed = dialog.winfo_reqwidth()
        assert needed <= support.PROMPT_WIDTH, (
            f"tresc okna potrzebuje {needed} px, a okno ma "
            f"{support.PROMPT_WIDTH} px - ostatni przycisk bedzie uciety"
        )
    finally:
        for widget in (dialog, root):
            try:
                widget.destroy()
            except Exception:
                pass


def test_help_windows_really_open(app, monkeypatch):
    """Wywoluje PRAWDZIWE funkcje okien, a nie ich atrapy.

    Regresja: app.py wolalo show_licence(root, config), a funkcja przyjmowala
    juz tylko master - blad sygnatury. Testy, ktore podmieniaja te funkcje,
    takiego bledu nie wykryja, bo nigdy nie uruchamiaja prawdziwego kodu.
    Ten test sprawdza tez, czy pliki z licencja i notami da sie odczytac.
    """
    tytuly = []

    monkeypatch.setattr(dialogs, "show_text",
                        lambda master, title, text, **k: tytuly.append((title, len(text))))

    app.open_licence()
    app.open_notices()
    app.open_about()

    nazwy = [tytul for tytul, _ in tytuly]
    assert "Licencja" in nazwy, f"nie otwarto licencji, otwarto: {nazwy}"
    assert any("Biblioteki" in nazwa for nazwa in nazwy), nazwy
    assert "O programie" in nazwy, nazwy

    # Kazde okno musi miec realna tresc, a nie komunikat o bledzie odczytu.
    for tytul, dlugosc in tytuly:
        assert dlugosc > 500, f"okno '{tytul}' ma tylko {dlugosc} znakow"
        assert not any(dlugosc == d for _t, d in tytuly if d < 100), \
            f"okno '{tytul}' wyglada na blad odczytu pliku"


def test_help_actions_do_not_crash(app, monkeypatch):
    """Kazda pozycja menu musi sie otwierac bez bledu (okna sa atrapami)."""
    opened = []
    monkeypatch.setattr(about, "show_about",
                        lambda *a, **k: opened.append("about"))
    monkeypatch.setattr(about, "show_licence",
                        lambda *a, **k: opened.append("licence"))
    monkeypatch.setattr(about, "show_third_party",
                        lambda *a, **k: opened.append("notices"))
    monkeypatch.setattr(about, "show_privacy",
                        lambda *a, **k: opened.append("privacy"))
    monkeypatch.setattr(about, "ask_message",
                        lambda *a, **k: opened.append("message"))

    app.open_about()
    app.open_licence()
    app.open_notices()
    app.open_privacy()
    app.write_to_author()

    assert opened == ["about", "licence", "notices", "privacy", "message"]


# --------------------------------------------------------------------------- #
# pliki i konwersja
# --------------------------------------------------------------------------- #
def test_adding_files_populates_rows_and_enables_button(app, sample_dir):
    app.add_paths([str(sample_dir)])

    assert len(app.files) == 3
    assert len(app.rows) == 3
    assert "3 pliki" in app.files_title.cget("text")
    assert str(app.convert_button.cget("state")) == "normal"

    app.remove_file(app.files[0])
    assert len(app.files) == 2

    app.clear_files()
    assert app.files == []
    assert str(app.convert_button.cget("state")) == "disabled"


def test_full_conversion_through_the_ui(app, sample_dir):
    app.add_paths([str(sample_dir)])
    app.start_conversion()
    pump(app)

    assert app.summary is not None
    assert app.summary.converted == 3

    statuses = [entry["status"].cget("text") for entry in app.rows.values()]
    assert statuses.count("gotowe") == 3
    assert "3 pliki" in app.summary_big.cget("text")
    assert "Skonwertowano: 3" in app.status_label.cget("text")

    assert (sample_dir / "IMG_0001.jpg").exists()
    assert (sample_dir / "wakacje" / "IMG_0003.jpg").exists()


def test_conversion_is_counted_for_support_prompts(app, sample_dir, values):
    """Po konwersji licznik musi wzrosnac - inaczej prosba nigdy sie nie pokaze."""
    assert app.values[store.KEY_CONVERTED_TOTAL] == 0

    app.add_paths([str(sample_dir)])
    app.start_conversion()
    pump(app)

    assert app.values[store.KEY_CONVERTED_TOTAL] == 3
    assert store.load()[store.KEY_CONVERTED_TOTAL] == 3


def test_cancel_button_stops_a_running_conversion(app, sample_dir, monkeypatch):
    import threading

    from heic2jpg import app as app_module
    from heic2jpg.converter import CANCELLED, FileResult, Summary

    worker_started = threading.Event()
    allow_work = threading.Event()

    def blocked_convert(files, options, on_progress=None, should_cancel=None):
        summary = Summary()
        for index, source in enumerate(files, start=1):
            worker_started.set()
            allow_work.wait(timeout=5)
            if should_cancel is not None and should_cancel():
                result = FileResult(source=source, status=CANCELLED, message="Anulowano.")
                summary.cancelled += 1
            else:
                result = FileResult(source=source, status="converted",
                                    bytes_before=10, bytes_after=5)
                summary.converted += 1
            summary.results.append(result)
            if on_progress:
                on_progress(index, len(files), result)
        return summary

    monkeypatch.setattr(app_module, "convert_files", blocked_convert)

    app.add_paths([str(sample_dir)])
    app.start_conversion()
    assert worker_started.wait(timeout=5), "watek konwersji nie wystartowal"

    app.cancel_conversion()
    assert app.cancel_event.is_set()
    allow_work.set()

    pump(app)
    assert app.summary.cancelled == len(app.files)
    assert app.summary.converted == 0
    assert str(app.convert_button.cget("state")) == "normal"


def test_progress_bar_reaches_the_end(app, sample_dir):
    app.add_paths([str(sample_dir)])
    app.start_conversion()
    pump(app)
    assert app.progress.get() == pytest.approx(1.0)


# --------------------------------------------------------------------------- #
# okno musi byc widoczne (regresja z Windows)
# --------------------------------------------------------------------------- #
def test_window_is_really_visible_after_mainloop_starts(values):
    """Okno musi byc widoczne po starcie petli zdarzen.

    Regresja: customtkinter na Windows w ``mainloop()`` chowa okno na moment,
    zeby ustawic kolor paska tytulu, i pokazuje je z powrotem TYLKO wtedy, gdy
    wczesniej nie wywolano ``withdraw()``. Wywolanie ``withdraw()`` przed
    ``mainloop()`` dawalo proces dzialajacy bez okna - okno migalo i znikalo.
    """
    import main as entry

    theme.apply_appearance()
    root = AppWindow()
    root.geometry("900x620")
    converter = None

    try:
        entry._set_alpha(root, 0.0)
        converter = ConverterApp(root, _Config, values)
        entry._set_alpha(root, 1.0)
        root.after(250, lambda: entry._ensure_window_visible(root))

        assert getattr(root, "_withdraw_called_before_window_exists", False) is False, (
            "wywolano withdraw() przed mainloop() - na Windows okno zostanie "
            "ukryte i uzytkownik zobaczy tylko migniecie"
        )

        observed = {}

        def inspect():
            observed["state"] = root.state()
            observed["viewable"] = root.winfo_viewable()
            converter._closing = True
            if converter._pump_id is not None:
                root.after_cancel(converter._pump_id)
                converter._pump_id = None
            root.quit()

        root.after(700, inspect)
        root.mainloop()

        assert observed.get("state") == "normal"
        assert observed.get("viewable") == 1, "okno istnieje, ale nie jest widoczne"
    finally:
        try:
            root.destroy()
        except Exception:
            pass
