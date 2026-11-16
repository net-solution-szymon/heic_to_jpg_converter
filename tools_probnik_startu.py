
import os
import sys
import time

# Etapy zapisujemy takze na ekranie - wersja z konsola pokaze je od razu.
def zapisz(gdzie: str, tekst: str) -> None:
    linia = f"[{time.strftime('%H:%M:%S')}] {tekst}"
    try:
        print(linia, flush=True)
    except Exception:
        pass
    for katalog in kandydaci():
        try:
            with (katalog / "probnik-startu.txt").open("a", encoding="utf-8") as f:
                f.write(linia + "\n")
            return
        except OSError:
            continue


def kandydaci():
    """Katalogi, w ktorych probujemy zapisac - po kolei."""
    wynik = []
    if getattr(sys, "frozen", False):
        wynik.append(os.path.dirname(os.path.abspath(sys.executable)))
        wynik.append(os.getcwd())
    else:
        wynik.append(os.path.dirname(os.path.abspath(__file__)))
    for zmienna in ("TEMP", "TMP", "USERPROFILE", "HOME"):
        sciezka = os.environ.get(zmienna)
        if sciezka:
            import pathlib
            wynik.append(pathlib.Path(sciezka))
    import pathlib
    return [pathlib.Path(p) for p in wynik]


def main() -> int:
    zapisz("", "=" * 60)
    zapisz("", "PROBNIK STARTU")
    zapisz("", f"Zamrozony   : {'tak' if getattr(sys, 'frozen', False) else 'nie'}")
    zapisz("", f"Python      : {sys.version.split()[0]}")
    zapisz("", f"Program     : {sys.executable}")
    zapisz("", f"Katalog     : {os.getcwd()}")
    zapisz("", "ETAP 1: program wystartowal i potrafi zapisac plik")

    zapisz("", "ETAP 2: ustawiam skalowanie ekranu (SetProcessDpiAwareness)")
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        zapisz("", "        OK")
    except Exception as exc:
        zapisz("", f"        pominiete: {type(exc).__name__}: {exc}")

    zapisz("", "ETAP 3: tworze okno")
    try:
        import tkinter
        zapisz("", "        tkinter zaimportowany")
        root = tkinter.Tk()
        zapisz("", "        okno utworzone")
        root.title("Probnik startu")
        root.geometry("420x160")
        zapisz("", "        okno pokazane")
        root.after(4000, root.destroy)
        root.mainloop()
        zapisz("", "        okno zamkniete")
    except Exception as exc:
        zapisz("", f"        BLAD: {type(exc).__name__}: {exc}")

    zapisz("", "ETAP 4: koniec - probnik przepracowal cala droge")
    zapisz("", "=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
