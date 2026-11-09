"""Testy startu programu i obslugi argumentow.

Powstaly po awarii na komputerze uzytkownika, gdzie program "mignal i znikal",
a `--diagnostic` nie zwracal NIC. Przyczyna byla taka, ze kilka sciezek
konczylo sie bez zadnej informacji:

  * `run_diagnostic` byl wolany POZA przechwytywaniem bledow,
  * raport diagnostyki powstawal dopiero na koncu, wiec przerwanie pracy
    nie zostawialo pliku,
  * nieznany argument (np. `-diagnostic` z jednym myslnikiem) byl po cichu
    pomijany, a bez konsoli nie bylo tego gdzie zobaczyc.

Efekt: kazda awaria wygladala identycznie - cisza. Te testy pilnuja, zeby tak
juz nie bylo.
"""
import sys

import pytest

import main


@pytest.fixture
def katalog_logow(tmp_path, monkeypatch):
    """Kieruje pliki raportow do katalogu tymczasowego.

    Bez tego testy pisalyby do katalogu projektu.
    """
    monkeypatch.setattr(main, "_candidate_dirs", lambda: [tmp_path])
    return tmp_path


# --------------------------------------------------------------------------- #
# argumenty
# --------------------------------------------------------------------------- #
def test_pojedynczy_myslnik_zamieniany_na_podwojny():
    """-diagnostic to najczestsza pomylka - musi dzialac jak --diagnostic."""
    assert main._normalise_arguments(["-diagnostic"]) == ["--diagnostic"]


def test_podwojny_myslnik_zostaje_bez_zmian():
    assert main._normalise_arguments(["--diagnostic"]) == ["--diagnostic"]


def test_krotka_opcja_nie_jest_psuta():
    """-h ma zostac -h, a nie zamienic sie w --h."""
    assert main._normalise_arguments(["-h"]) == ["-h"]


def test_sciezka_pliku_nie_jest_ruszana():
    assert main._normalise_arguments(["--test-file", "foto.HEIC"]) == [
        "--test-file", "foto.HEIC"]


def test_obcy_argument_nie_jest_ruszany():
    """Nieznanego argumentu nie zmieniamy - tylko go zglaszamy."""
    assert main._normalise_arguments(["--cokolwiek"]) == ["--cokolwiek"]


def test_pojedynczy_myslnik_naprawde_uruchamia_diagnostyke(monkeypatch):
    wywolania = []
    monkeypatch.setattr(main, "run_diagnostic",
                        lambda plik="": wywolania.append(plik) or 0)
    monkeypatch.setattr(sys, "argv", ["main.py", "-diagnostic"])

    assert main.main() == 0
    assert wywolania == [""]

    # Kontrola: bez zamiany argumentu program poszedlby sciezka okna.
    assert main._normalise_arguments(["-diagnostic"]) == ["--diagnostic"]


def test_nieznany_argument_jest_zglaszany_w_spakowanej_wersji(monkeypatch,
                                                              katalog_logow):
    """Nieznany argument nie moze znikac po cichu.

    Wersja spakowana nie ma konsoli, wiec komunikat MUSI byc oknem - inaczej
    uzytkownik znow nie zobaczy nic.
    """
    zgloszone = []
    monkeypatch.setattr(main, "_show_error_box",
                        lambda tytul, tekst: zgloszone.append(tytul))
    monkeypatch.setattr(main, "run_app", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["main.py", "--cos-dziwnego"])
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    main.main()

    assert zgloszone == ["Nieznany argument"]
    zapisany = (katalog_logow / "nieznane-argumenty.txt").read_text(encoding="utf-8")
    assert "--cos-dziwnego" in zapisany
    assert "--diagnostic" in zapisany      # podpowiedz, jak jest poprawnie


def test_nieznany_argument_ze_zrodel_trafia_na_konsole(monkeypatch, katalog_logow,
                                                       capsys):
    """Uruchomienie ze zrodel ma terminal - tam okno byloby zbedne."""
    monkeypatch.setattr(main, "_show_error_box",
                        lambda *a: pytest.fail("okno nie powinno sie pokazac"))
    monkeypatch.setattr(main, "run_app", lambda: 0)
    monkeypatch.setattr(sys, "argv", ["main.py", "--cos-dziwnego"])

    main.main()

    assert "--cos-dziwnego" in capsys.readouterr().out
    assert (katalog_logow / "nieznane-argumenty.txt").is_file()


# --------------------------------------------------------------------------- #
# slad startu
# --------------------------------------------------------------------------- #
def test_slad_startu_powstaje(monkeypatch, katalog_logow):
    """Plik start.txt odpowiada na pytanie: czy program w ogole wystartowal?"""
    main._log_start()

    tekst = (katalog_logow / "start.txt").read_text(encoding="utf-8")
    assert "Python" in tekst
    assert "Argumenty" in tekst
    assert "Zamrozony" in tekst


# --------------------------------------------------------------------------- #
# awarie nie moga konczyc sie cisza
# --------------------------------------------------------------------------- #
def test_blad_w_diagnostyce_jest_zglaszany(monkeypatch, katalog_logow):
    """KLUCZOWY TEST.

    Wczesniej `run_diagnostic` byl wolany poza zabezpieczeniem, wiec wyjatek
    w nim konczyl program bez zadnego sladu.
    """
    zgloszone = []
    monkeypatch.setattr(main, "_report_failure",
                        lambda tytul, komunikat, szczegoly="": zgloszone.append(
                            (tytul, komunikat)))

    def wybuch(plik=""):
        raise RuntimeError("awaria w diagnostyce")

    monkeypatch.setattr(main, "run_diagnostic", wybuch)
    monkeypatch.setattr(sys, "argv", ["main.py", "--diagnostic"])

    kod = main.main()

    assert kod == 5, "blad powinien zwrocic kod 5"
    assert zgloszone, "blad nie zostal zgloszony - znow cisza"
    assert "awaria w diagnostyce" in zgloszone[0][1]


def test_blad_w_uruchomieniu_okna_jest_zglaszany(monkeypatch, katalog_logow):
    zgloszone = []
    monkeypatch.setattr(main, "_report_failure",
                        lambda tytul, komunikat, szczegoly="": zgloszone.append(tytul))

    def wybuch():
        raise RuntimeError("awaria okna")

    monkeypatch.setattr(main, "run_app", wybuch)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    assert main.main() == 5
    assert zgloszone == ["Nieoczekiwany blad"]


def test_brak_bibliotek_ma_wlasny_komunikat(monkeypatch, katalog_logow):
    zgloszone = []
    monkeypatch.setattr(main, "_report_failure",
                        lambda tytul, komunikat, szczegoly="": zgloszone.append(tytul))

    def wybuch():
        raise main.StartupError("brakuje bibliotek")

    monkeypatch.setattr(main, "run_app", wybuch)
    monkeypatch.setattr(sys, "argv", ["main.py"])

    assert main.main() == 1
    assert zgloszone == ["Nie mozna uruchomic programu"]


# --------------------------------------------------------------------------- #
# raport diagnostyki
# --------------------------------------------------------------------------- #
def test_raport_diagnostyki_powstaje_od_razu(monkeypatch, katalog_logow):
    sciezka = main._open_log("diagnostyka.txt")
    main._append_line(sciezka, "pierwsza linia")

    assert (katalog_logow / "diagnostyka.txt").read_text(
        encoding="utf-8") == "pierwsza linia\n"


def test_raport_jest_zapisywany_podczas_pracy(monkeypatch, katalog_logow,
                                              isolated_data):
    """Gdyby diagnostyka przerwala sie w polowie, raport i tak musi istniec.

    Sprawdzamy zawartosc pliku W TRAKCIE pracy - w momencie, gdy program
    jeszcze nie doszedl do konca.
    """
    widziane = {}

    def podmienione(cfg):
        plik = katalog_logow / "diagnostyka.txt"
        widziane["tekst"] = plik.read_text(encoding="utf-8") if plik.exists() else ""
        return ["Polaczenie    : (test)"]

    monkeypatch.setattr(main, "_check_connection", podmienione)

    main.run_diagnostic()

    assert "diagnostyka" in widziane["tekst"], (
        "raport nie byl zapisywany na biezaco - przerwanie pracy zostawiloby "
        "pusty plik")


def test_diagnostyka_konczy_sie_poprawnie(monkeypatch, katalog_logow,
                                          isolated_data):
    monkeypatch.setattr(main, "_check_connection",
                        lambda cfg: ["Polaczenie    : (test)"])

    kod = main.run_diagnostic()
    tekst = (katalog_logow / "diagnostyka.txt").read_text(encoding="utf-8")

    assert kod in (0, 1)
    assert "HEIC -> JPG Converter - diagnostyka" in tekst
    assert "Polaczenie" in tekst
    assert "WNIOSEK" in tekst


def test_diagnostyka_bez_configu_nie_wybucha(monkeypatch, katalog_logow,
                                             isolated_data):
    """Uszkodzony config.py ma byc opisany, a nie przerwac raportu."""
    monkeypatch.setattr(main, "_check_connection",
                        lambda cfg: (_ for _ in ()).throw(RuntimeError("zly config")))

    kod = main.run_diagnostic()

    tekst = (katalog_logow / "diagnostyka.txt").read_text(encoding="utf-8")
    assert "Konfiguracja" in tekst
    assert kod in (0, 1)
