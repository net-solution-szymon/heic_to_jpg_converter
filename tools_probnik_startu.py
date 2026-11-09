"""Probnik startu - narzedzie do diagnozy na komputerze, gdzie program ginie.

PO CO TO JEST
-------------
Na komputerze z wlaczonym VPN program ginie z kodem 0xc0000374 (uszkodzenie
sterty), zanim zdazy cokolwiek zapisac. Nie wiadomo, czy wine ponosi nasz kod,
czy samo pakowanie PyInstallera (wersja jednoplikowa rozpakowuje sie do
katalogu tymczasowego i uruchamia stamtad).

Ten probnik nic nie liczy i nic nie konwertuje. Zapisuje po jednej linii na
kazdym etapie startu i pokazuje, DO KTOREGO MIEJSCA dochodzi.

JAK UZYC
--------
Na komputerze z Pythonem i PyInstallerem:

    pyinstaller --onefile --console tools_probnik_startu.py

Powstanie dist\\tools_probnik_startu.exe. Skopiuj go na komputer, gdzie
program sie nie uruchamia, i uruchom. Potem znajdz plik probnik-startu.txt
(obok programu, w katalogu tymczasowym albo w katalogu uzytkownika) i przyslij
jego tresc.

DODATKOWO warto powtorzyc test w wersji folderowej - podmien --onefile na
--onedir. Jesli wersja folderowa dziala, a jednoplikowa nie, to znaczy, ze
problem jest w rozpakowywaniu do katalogu tymczasowego.

JAK CZYTAC WYNIK
----------------
    brak jakiegokolwiek pliku   -> proces nie wykonal ani jednej linijki;
                                   zatrzymuje go system albo rozpakowywanie
    plik konczy sie na etapie 1 -> nie udalo sie zapisac pliku (prawa dostepu)
    plik konczy sie na etapie 2 -> winne jest ustawienie skalowania ekranu
    plik konczy sie na etapie 3 -> winna jest biblioteka okien (tkinter)
    plik dochodzi do konca      -> probnik dziala; problem jest w programie
"""
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
