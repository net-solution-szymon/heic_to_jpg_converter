"""Punkt wejścia programu.

    python main.py                     uruchomienie normalne
    python main.py --diagnostic        sprawdzenie instalacji (bez okna)
    python main.py --diagnostic --test-file zdjecie.HEIC

Zasada, ktorej trzyma sie ten plik: **program nigdy nie konczy sie po cichu**.
Jesli czegokolwiek brakuje albo cokolwiek pojdzie nie tak, uzytkownik zobaczy
okno z wyjasnieniem, a tresc trafi do pliku obok programu. Bez tego blad
konczy sie "mignieciem okna", ktorego nie da sie zdiagnozowac.
"""
from __future__ import annotations

import platform
import sys
import time
import traceback
from pathlib import Path

# Uruchomienie ze zrodel: katalog skryptu. Wersja spakowana (PyInstaller):
# katalog pliku .exe, zeby znalezc config.py i katalog legal/ lezace obok
# programu - sys.path[0] wskazuje wtedy wnetrze paczki.
if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).resolve().parent
else:
    BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


class StartupError(Exception):
    """Blad uniemozliwiajacy uruchomienie, z instrukcja dla uzytkownika."""


# (nazwa modulu, nazwa pakietu do pip, do czego sluzy)
REQUIRED_MODULES = [
    ("tkinter", None, "interfejs graficzny (jest czescia Pythona)"),
    ("PIL", "pillow", "przetwarzanie obrazow"),
    ("pi_heif", "pi-heif", "obsluga formatu HEIC"),
    ("customtkinter", "customtkinter", "wyglad interfejsu"),
    ("tkinterdnd2", "tkinterdnd2", "przeciaganie plikow"),
    ("httpx", "httpx", "wysylka anonimowych statystyk"),
]


def enable_hidpi() -> None:
    """Ostry tekst przy skalowaniu Windows powyzej 100%."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _attach_console() -> None:
    """Podlacza okno konsoli do programu zbudowanego BEZ konsoli.

    Wersja spakowana jest budowana z console=False, wiec na Windows nie ma
    wlasnej konsoli i `print()` trafia w proznice. AttachConsole podlacza sie
    do konsoli wywolujacego. Gdy sie nie uda (uruchomienie z dwukliku), wynik
    i tak zostanie zapisany do pliku.
    """
    if not sys.platform.startswith("win") or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes

        if not ctypes.windll.kernel32.AttachConsole(-1):
            return
        for name in ("stdout", "stderr"):
            try:
                setattr(sys, name, open("CONOUT$", "w", encoding="utf-8", buffering=1))
            except OSError:
                pass
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    except Exception:
        pass


def _candidate_dirs() -> list[Path]:
    """Gdzie probowac zapisac log - obok programu, potem katalog biezacy, domowy."""
    candidates = []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent)
    candidates.append(BASE)
    candidates.append(Path.cwd())
    candidates.append(Path.home())
    return candidates


def _save_text(filename: str, content: str) -> Path | None:
    for directory in _candidate_dirs():
        try:
            target = directory / filename
            target.write_text(content, encoding="utf-8")
            return target
        except OSError:
            continue
    return None


def _open_log(filename: str) -> Path | None:
    """Tworzy (albo czysci) plik raportu i zwraca jego sciezke.

    Sciezke ustalamy RAZ. Gdyby katalog okazal sie nie do zapisu w trakcie
    pracy, nie chcemy rozbic jednego raportu na dwa pliki.
    """
    for directory in _candidate_dirs():
        try:
            target = directory / filename
            target.write_text("", encoding="utf-8")
            return target
        except OSError:
            continue
    return None


def _append_line(target: Path | None, text: str) -> None:
    """Dopisuje linie do pliku raportu. Blad zapisu nie moze przerwac pracy."""
    if target is None:
        return
    try:
        with target.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")
    except OSError:
        pass


def _log_start() -> None:
    """Zapisuje slad tuz po starcie Pythona.

    Ten plik odpowiada na jedno pytanie: czy program zdazyl wykonac choc jedna
    wlasna linijke? Jesli pliku nie ma, to zatrzymal go system, a nie nasz kod
    - i szukanie bledu w kodzie jest wtedy strata czasu.
    """
    _save_text("start.txt", (
        f"Uruchomiono : {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"Python      : {sys.version}\n"
        f"Zamrozony   : {'tak' if getattr(sys, 'frozen', False) else 'nie'}\n"
        f"Katalog     : {BASE}\n"
        f"Argumenty   : {sys.argv[1:]}\n"
        f"System      : {platform.platform()}\n"
    ))


def _show_error_box(title: str, message: str) -> None:
    """Okno z bledem. Celowo czysty tkinter, nie customtkinter.

    Gdy zawiodl wlasnie customtkinter, okno i tak musi sie pokazac - dlatego
    nie korzystamy tu z biblioteki, ktora mogla byc przyczyna problemu.
    """
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:
        try:
            print(f"\n{title}\n{'-' * len(title)}\n{message}\n")
        except Exception:
            pass


def _report_failure(title: str, message: str, details: str = "") -> Path | None:
    """Pokazuje blad i zapisuje log. Uzywane przy kazdym nieudanym starcie."""
    stamp = f"{title}\n{'=' * 70}\n\n{message}\n"
    if details:
        stamp += f"\nSzczegoly techniczne:\n{details}\n"
    stamp += (f"\nPython: {sys.version}\nZamrozony: "
              f"{'tak' if getattr(sys, 'frozen', False) else 'nie'}\nKatalog: {BASE}\n")

    target = _save_text("blad-startu.txt", stamp)

    full = message
    if target is not None:
        full += f"\n\nSzczegoly zostaly zapisane w pliku:\n{target}"
    else:
        full += "\n\n(Nie udalo sie zapisac pliku z bledem.)"

    _show_error_box(title, full)
    return target


# --------------------------------------------------------------------------- #
# diagnostyka
# --------------------------------------------------------------------------- #
def _check_connection(cfg) -> list[str]:
    """Sprawdza, czy serwer statystyk odpowiada. Zwraca gotowe linie raportu.

    Bez tego diagnostyka odpowiada tylko na pytanie "czy biblioteki sa na
    miejscu", a milczy o najczestszej przyczynie klopotow: ze siec nie
    przepuszcza ruchu. Tu sprawdzamy naprawde i mowimy, jakim wejsciem
    program probuje sie polaczyc.
    """
    import time

    from heic2jpg import telemetry

    adres = (getattr(cfg, "SERVER_URL", "") or "").rstrip("/")
    if not adres:
        return ["Serwer        : (brak adresu - statystyki wylaczone)"]

    linie = [f"Serwer        : {adres}"]

    try:
        import httpx

        poczatek = time.monotonic()
        odpowiedz = httpx.get(f"{adres}/api/v1/health",
                              timeout=getattr(cfg, "TELEMETRY_TIMEOUT", 6.0))
        milisekundy = int((time.monotonic() - poczatek) * 1000)
        if odpowiedz.status_code == 200:
            linie.append(f"Polaczenie    : OK (odpowiedz w {milisekundy} ms)")
        else:
            linie.append(f"Polaczenie    : serwer odpowiedzial "
                         f"{odpowiedz.status_code}")
    except Exception as exc:  # noqa: BLE001 - kazda przyczyna jest pouczajaca
        linie.append("Polaczenie    : BLAD")
        linie.append(f"                 {telemetry._human_reason(exc, cfg)}")

    return linie


def run_diagnostic(test_file: str = "") -> int:
    """Wypisuje informacje o instalacji i (opcjonalnie) sprawdza plik HEIC.

        HEIC-to-JPG-Converter.exe --diagnostic
        HEIC-to-JPG-Converter.exe --diagnostic --test-file zdjecie.HEIC

    Wynik trafia jednoczesnie na konsole i do pliku ``diagnostyka.txt``.
    """
    _attach_console()

    # Raport zapisujemy linia po linii. Gdyby cos przerwalo prace w polowie,
    # plik i tak pokaze, jak daleko program doszedl - a to jest cala wartosc
    # tej diagnostyki.
    log_path = _open_log("diagnostyka.txt")
    lines: list[str] = []

    def say(text: str = "") -> None:
        lines.append(text)
        print(text)
        _append_line(log_path, text)

    say("HEIC -> JPG Converter - diagnostyka")
    say("=" * 60)
    say(f"Python        : {sys.version.split()[0]} na {platform.machine()}"
        f" ({64 if sys.maxsize > 2**32 else 32}-bit)")
    say(f"Zamrozony     : {'tak' if getattr(sys, 'frozen', False) else 'nie'}")
    say(f"Katalog       : {BASE}")
    say("")

    say("-- biblioteki --")
    missing: list[str] = []
    for module, package, purpose in REQUIRED_MODULES:
        try:
            imported = __import__(module)
            version = getattr(imported, "__version__", "")
            extra = f" {version}" if version else ""
            say(f"  OK      {module:<14}{extra:<10} ({purpose})")
        except Exception as exc:
            say(f"  BRAK    {module:<14}{'':<10} ({purpose})")
            say(f"          -> {type(exc).__name__}: {exc}")
            if package:
                missing.append(package)

    if missing:
        say("")
        say("  BRAKUJE BIBLIOTEK. Zainstaluj je poleceniem:")
        say(f"      {Path(sys.executable).name} -m pip install " + " ".join(missing))

    try:
        import pi_heif

        say("")
        say(f"libheif       : {pi_heif.libheif_version()}")
    except Exception:
        pass

    try:
        from heic2jpg.converter import register_heif

        say(f"Rejestracja HEIF: {'OK' if register_heif() else 'NIEUDANA'}")
    except Exception as exc:
        say(f"Rejestracja HEIF: BLAD - {type(exc).__name__}: {exc}")

    say("")
    say("-- konfiguracja --")
    try:
        import config as cfg
        from heic2jpg import store

        say(f"Program       : {cfg.APP_NAME} {cfg.APP_VERSION}")
        for linia in _check_connection(cfg):
            say(linia)
        say(f"Wsparcie      : {cfg.SUPPORT_URL or '(brak - uzupelnij SUPPORT_URL)'}")
        say(f"Repozytorium  : {cfg.GITHUB_URL or '(nie ustawiono)'}")

        values = store.load()
        say(f"Plik danych   : {store.data_file()}")
        say(f"Statystyki    : {'wlaczone' if values.get(store.KEY_TELEMETRY, True) else 'WYLACZONE'}")
        say(f"Instalacja    : {values.get(store.KEY_INSTALL_ID) or '(jeszcze nie nadany)'}")
        say(f"Konwersji     : {values.get(store.KEY_CONVERTED_TOTAL, 0)}")
        say(f"Uruchomien    : {values.get(store.KEY_SESSIONS, 0)}")
    except Exception as exc:
        say(f"Konfiguracja  : BLAD - {type(exc).__name__}: {exc}")

    exit_code = 0
    if test_file:
        path = Path(test_file)
        say("")
        say(f"-- test pliku: {path} --")
        if not path.is_file():
            say("Wynik         : plik nie istnieje")
            exit_code = 3
        else:
            try:
                from PIL import Image, ImageOps

                with Image.open(path) as image:
                    frames = getattr(image, "n_frames", 1)
                    say(f"Otwarto       : {image.format} {image.mode} {image.size}, "
                        f"klatek: {frames}")
                    out = path.with_suffix(".diagnostic.jpg")
                    ImageOps.exif_transpose(image).convert("RGB").save(
                        out, "JPEG", quality=90)
                    say(f"Konwersja     : OK -> {out} ({out.stat().st_size} B)")
                    out.unlink(missing_ok=True)
            except Exception as exc:
                say(f"Wynik         : BLAD - {type(exc).__name__}: {exc}")
                exit_code = 4

    say("=" * 60)
    if missing:
        say("WNIOSEK: brakuje bibliotek - program nie uruchomi sie, dopoki ich nie")
        say("zainstalujesz (polecenie powyzej).")
        exit_code = 1
    else:
        say("WNIOSEK: srodowisko wyglada dobrze.")

    report = _save_text("diagnostyka.txt", "\n".join(lines))
    if report is not None:
        print()
        print(f"Raport zapisany w pliku: {report}")

    return exit_code


# --------------------------------------------------------------------------- #
# uruchomienie okna
# --------------------------------------------------------------------------- #
def check_dependencies() -> None:
    """Podnosi StartupError z konkretna instrukcja, jesli czegos brakuje."""
    missing = []
    for module, package, purpose in REQUIRED_MODULES:
        try:
            __import__(module)
        except Exception as exc:  # noqa: BLE001
            hint = f"pip install {package}" if package else "napraw instalacje Pythona"
            missing.append(f"  - {module} ({purpose})\n      {hint}\n      "
                           f"{type(exc).__name__}: {exc}")

    if missing:
        raise StartupError(
            "Brakuje bibliotek potrzebnych do uruchomienia programu:\n\n"
            + "\n".join(missing)
            + "\n\nUruchom w oknie wiersza polecen:\n"
              f"    {Path(sys.executable).name} -m pip install -r requirements.txt"
        )


def _set_alpha(root, value: float) -> None:
    """Ustawia przezroczystosc okna, jesli system to obsluguje."""
    try:
        root.attributes("-alpha", value)
    except Exception:
        # Brak wsparcia dla -alpha (czesc serwerow X bez kompozytora).
        # Okno bedzie po prostu widoczne od razu - to nie jest blad.
        pass


def _ensure_window_visible(root) -> None:
    """Awaryjne pokazanie okna, gdyby zostalo ukryte przez biblioteke.

    Przywracamy tez pelna nieprzezroczystosc. Okno jest chwilowo ustawiane na
    `-alpha 0.0`, zeby nie mrugnelo przy starcie - gdyby przywrocenie sie nie
    udalo, program dzialalby dalej, ale bylby NIEWIDOCZNY. Ten bezpiecznik
    uruchamia sie 250 ms po starcie i zawsze konczy z pelnym kryciem.
    """
    try:
        if root.state() != "normal":
            root.deiconify()
        root.lift()
        root.focus_force()
    except Exception:
        pass
    try:
        root.attributes("-alpha", 1.0)
    except Exception:
        pass


def run_app() -> int:
    check_dependencies()

    import config

    from heic2jpg import about, store, support, telemetry, theme
    from heic2jpg.app import ConverterApp
    from heic2jpg.converter import register_heif
    from heic2jpg.window import AppWindow

    # Remembered state: counters, preferences, the installation identifier.
    values = store.load()
    first_run = not values.get(store.KEY_INSTALL_ID)
    telemetry.ensure_identity(values)
    support.start_session(values)

    theme.apply_appearance()
    register_heif()

    root = AppWindow()
    root.title(getattr(config, "APP_TITLE",
                       getattr(config, "APP_NAME", "HEIC --> JPG Converter")))
    root.geometry("1160x864")
    root.minsize(1000, 720)
    root.configure(fg_color=theme.Palette.bg)
    # UWAGA - nie wolno tu wolac root.withdraw().
    #
    # customtkinter na Windows, w mainloop(), sam chowa okno na moment, zeby
    # ustawic kolor paska tytulu (DwmSetWindowAttribute), a potem pokazuje je
    # z powrotem - ale WYLACZNIE wtedy, gdy uzytkownik nie schowal okna
    # wczesniej. Flaga _withdraw_called_before_window_exists jest ustawiana
    # przez withdraw() i blokuje to przywrocenie. Efekt: okno mignie i zniknie,
    # a proces dalej dziala (widac go w menedzerze zadan, okna nie ma).
    # Dlatego zamiast chowac okno, robimy je przezroczystym. Gdyby system nie
    # obslugiwal przezroczystosci, okno po prostu pokaze sie od razu.
    try:
        root.attributes("-alpha", 0.0)
    except Exception:
        pass

    ConverterApp(root, config, values)

    _set_alpha(root, 1.0)
    root.after(250, lambda: _ensure_window_visible(root))

    if first_run:
        # Nothing is reported until the user has been told what is reported.
        def after_notice() -> None:
            about.first_run_notice(root, config, values)
            telemetry.send_statistics_in_background(values, config)

        root.after(400, after_notice)
    else:
        telemetry.send_statistics_in_background(values, config)

    root.mainloop()

    store.save(values)
    return 0


KNOWN_OPTIONS = ("--diagnostic", "--test-file")


def _normalise_arguments(argv: list[str]) -> list[str]:
    """Zamienia pojedynczy myslnik na podwojny: -diagnostic -> --diagnostic.

    Uzytkownicy czesto pisza jeden myslnik. argparse uznaje wtedy argument za
    nieznany, a bez konsoli program nie mowi o tym ani slowem - startuje
    normalnie i wyglada to tak, jakby argument zostal zignorowany.
    """
    wynik = []
    for element in argv:
        if (element.startswith("-") and not element.startswith("--")
                and len(element) > 2 and "-" + element in KNOWN_OPTIONS):
            wynik.append("-" + element)
        else:
            wynik.append(element)
    return wynik


def _report_unknown_arguments(unknown: list[str]) -> None:
    """Nieznane argumenty nie moga znikac po cichu - uzytkownik musi wiedziec."""
    tekst = ("Program nie rozpoznal tych argumentow:\n\n    "
             + " ".join(unknown)
             + "\n\nPrzyjmowane argumenty:\n\n"
               "    --diagnostic\n"
               "        wypisz informacje o instalacji i zakoncz (bez okna)\n\n"
               "    --diagnostic --test-file zdjecie.HEIC\n"
               "        dodatkowo sprawdz dzialanie na wskazanym pliku\n")
    _save_text("nieznane-argumenty.txt", tekst)
    if getattr(sys, "frozen", False):
        _show_error_box("Nieznany argument", tekst)
    else:
        print(tekst)


def main() -> int:
    """Punkt wejscia. NIC nie moze stad wyjsc po cichu.

    Uwaga na zakres: zabezpieczenie obejmuje CALA prace, takze tryb
    --diagnostic. Wczesniej diagnostyka byla wolana poza nim, wiec blad w niej
    konczyl program bez sladu - a bez konsoli nie bylo tego gdzie zobaczyc.
    """
    try:
        return _main()
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 - nic nie moze zginac po cichu
        _report_failure(
            "Nieoczekiwany blad",
            f"{type(exc).__name__}: {exc}",
            traceback.format_exc(),
        )
        return 5


def _main() -> int:
    enable_hidpi()
    _log_start()

    import argparse

    parser = argparse.ArgumentParser(
        prog="HEIC-to-JPG-Converter", add_help=True,
        description="HEIC -> JPG Converter")
    parser.add_argument("--diagnostic", action="store_true",
                        help="wypisz informacje o instalacji i zakoncz (bez okna)")
    parser.add_argument("--test-file", default="",
                        help="plik HEIC do sprawdzenia w trybie --diagnostic")
    args, unknown = parser.parse_known_args(_normalise_arguments(sys.argv[1:]))

    if unknown:
        _report_unknown_arguments(unknown)

    if args.diagnostic:
        return run_diagnostic(args.test_file)

    try:
        return run_app()
    except StartupError as exc:
        _report_failure("Nie mozna uruchomic programu", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
