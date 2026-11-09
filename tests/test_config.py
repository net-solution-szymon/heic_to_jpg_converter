"""Testy pliku konfiguracji, ktory trafia do wydania.

Ten plik jest jedynym, ktory uzytkownik edytuje przed zbudowaniem programu.
Latwo w nim o pomylke, ktorej zaden inny test nie widzi - dlatego sprawdzamy
wartosci, ktore zobaczy czlowiek: nazwe w pasku okna i adresy.
"""
import config


def test_tytul_okna_zawiera_autora():
    """W pasku okna ma byc pelna nazwa z autorem - wymog wlasciciela programu."""
    assert config.APP_TITLE == "HEIC --> JPG Converter by Szymon Jankojć"


def test_tytul_zaczyna_sie_od_nazwy_programu():
    assert config.APP_TITLE.startswith("HEIC")


def test_nazwa_krotka_nadal_istnieje():
    """APP_NAME jest uzywane w oknie "O programie" i w diagnostyce."""
    assert config.APP_NAME


def test_adresy_serwera_i_wsparcia_sa_uzupelnione():
    assert config.SERVER_URL.startswith("https://")
    assert config.SUPPORT_URL.startswith("https://")
    assert config.GITHUB_URL.startswith("https://")


def test_w_konfiguracji_nie_zostaly_zapowiedzi():
    """Pola do uzupelnienia zapisujemy w nawiasach kwadratowych."""
    for nazwa in ("SERVER_URL", "SUPPORT_URL", "GITHUB_URL", "APP_TITLE"):
        wartosc = getattr(config, nazwa, "")
        assert "[" not in str(wartosc), f"{nazwa} wyglada na nieuzupelnione: {wartosc}"
