"""Testy wykrywania serwera proxy.

Sedno: program ma dzialac w sieci firmowej bez wpisywania czegokolwiek przez
uzytkownika, a sposob ustalania proxy ma byc tak prosty, zeby nie mial jak
zepsuc programu.

DLACZEGO TE TESTY WYGLADAJA TAK, A NIE INACZEJ
-----------------------------------------------
Poprzednia wersja pytala system przez API WinHTTP (ctypes, wlasne struktury,
zwalnianie pamieci przez GlobalFree). Pomylka w zwalnianiu pamieci skonczyla
sie uszkodzeniem sterty i smiercia programu na komputerze uzytkownika
(kod 0xc0000374), bez sladu i bez mozliwosci zdiagnozowania.

Dlatego na koncu tego pliku jest test, ktory pilnuje, zeby ctypes i GlobalFree
NIE WROCILY do tego modulu. To jest wazniejsze niz same funkcje.
"""
import ctypes
import os
import sys

import pytest

from heic2jpg import netproxy

SCIECZKA_UZYTKOWNIKA = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
SCIECZKA_ZASAD = (r"SOFTWARE\Policies\Microsoft\Windows"
                  r"\CurrentVersion\Internet Settings")


class Config:
    SERVER_URL = "https://przyklad.example"
    TELEMETRY_TIMEOUT = 1
    PROXY_URL = ""


@pytest.fixture(autouse=True)
def czysty_stan(monkeypatch):
    """Kazdy test startuje bez zmiennych srodowiskowych i bez stanu z poprzedniego.

    Zapamietujemy cale srodowisko, bo `apply` wpisuje do niego bezposrednio,
    a monkeypatch cofa tylko to, co sam zmienil.
    """
    zapas = dict(os.environ)
    for nazwa in netproxy.ENV_VARIABLES:
        monkeypatch.delenv(nazwa, raising=False)
    monkeypatch.setattr(netproxy, "_ustawione", None)
    monkeypatch.setattr(netproxy, "_zrodlo", "nie sprawdzano")
    yield monkeypatch
    os.environ.clear()
    os.environ.update(zapas)


# --------------------------------------------------------------------------- #
# normalizacja adresu
# --------------------------------------------------------------------------- #
def test_adres_bez_protokolu_dostaje_http():
    assert netproxy._clean_proxy("proxy:8080") == "http://proxy:8080"


def test_adres_z_protokolem_zostaje_bez_zmian():
    assert netproxy._clean_proxy("http://proxy:8080") == "http://proxy:8080"


def test_wybiera_wpis_dla_https():
    assert netproxy._clean_proxy("http=p:80;https=p:443") == "http://p:443"


def test_bez_wpisu_https_bierze_http():
    assert netproxy._clean_proxy("http=p:80") == "http://p:80"


def test_kilka_serwerow_bierze_pierwszy():
    assert netproxy._clean_proxy("p1:80;p2:80") == "http://p1:80"


def test_direct_znaczy_bez_proxy():
    assert netproxy._clean_proxy("DIRECT") == ""


def test_pusty_adres_daje_pusty_wynik():
    assert netproxy._clean_proxy("") == ""
    assert netproxy._clean_proxy("   ") == ""


def test_sam_direct_wsrod_serwerow():
    assert netproxy._clean_proxy("DIRECT;proxy:80") == "http://proxy:80"


# --------------------------------------------------------------------------- #
# zmienne srodowiskowe
# --------------------------------------------------------------------------- #
def test_env_proxy_zwraca_wartosc_czytelna_dla_httpx(czysty_stan):
    czysty_stan.setenv("HTTP_PROXY", "proxy.firma.pl:8080")
    assert netproxy.env_proxy() == "http://proxy.firma.pl:8080"


def test_env_proxy_bez_ustawien():
    assert netproxy.env_proxy() is None


# --------------------------------------------------------------------------- #
# rejestr Windows
# --------------------------------------------------------------------------- #
class _FalszywyWinreg:
    """Podstawia modul winreg, zeby testowac czytanie rejestru na Linuksie.

    Obsluguje podklucze, bo prawdziwy magazyn WinHTTP lezy w podkluczu
    ``Connections`` - bez tego nie daloby sie sprawdzic jego odczytu.
    """

    HKEY_CURRENT_USER = "HKCU"
    HKEY_LOCAL_MACHINE = "HKLM"

    def __init__(self, wartosci):
        self._wartosci = wartosci

    class _Klucz:
        def __init__(self, dane, hive="", sciezka=""):
            self.dane = dane
            self.hive = hive
            self.sciezka = sciezka

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def OpenKey(self, galaz, sciezka):
        if isinstance(galaz, _FalszywyWinreg._Klucz):
            hive = galaz.hive
            pelna = f"{galaz.sciezka}\\{sciezka}"
        else:
            hive = galaz
            pelna = sciezka
        dane = self._wartosci.get((hive, pelna))
        if dane is None:
            raise OSError("brak klucza")
        return _FalszywyWinreg._Klucz(dane, hive, pelna)

    def QueryValueEx(self, klucz, nazwa):
        if nazwa not in klucz.dane:
            raise OSError("brak wartosci")
        return klucz.dane[nazwa], 1


def _podstaw_rejestr(monkeypatch, wartosci):
    import sys as _sys
    monkeypatch.setitem(_sys.modules, "winreg", _FalszywyWinreg(wartosci))


def test_rejestr_czyta_proxy_uzytkownika(monkeypatch):
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {"ProxyEnable": 1,
                                        "ProxyServer": "srv01prox.corp:80"},
    })
    adres, opis = netproxy._from_registry()
    assert adres == "http://srv01prox.corp:80"
    assert "uzytkownika" in opis


def test_rejestr_ignoruje_wylaczone_proxy(monkeypatch):
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {"ProxyEnable": 0,
                                        "ProxyServer": "srv01prox.corp:80"},
    })
    adres, _opis = netproxy._from_registry()
    assert adres is None


def test_rejestr_bez_klucza_nie_wybucha(monkeypatch):
    _podstaw_rejestr(monkeypatch, {})
    adres, opis = netproxy._from_registry()
    assert adres is None
    assert opis


def test_zasady_firmowe_brane_gdy_brak_ustawien_uzytkownika(monkeypatch):
    """Na komputerach firmowych proxy czesto ustawia polityka, nie uzytkownik."""
    _podstaw_rejestr(monkeypatch, {
        ("HKLM", SCIECZKA_ZASAD): {"ProxyEnable": 1,
                                   "ProxyServer": "proxy.firma.pl:8080"},
    })
    adres, opis = netproxy._from_registry()
    assert adres == "http://proxy.firma.pl:8080"
    assert "zasady" in opis.lower() or "zasad" in opis


def test_pac_jest_zglaszany_ale_nie_odczytywany(monkeypatch):
    """Pliku PAC nie rozwiazemy bez kodu systemowego - mowimy o tym wprost."""
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {"ProxyEnable": 1,
                                        "AutoConfigURL": "http://wpad/pac"},
    })
    adres, opis = netproxy._from_registry()
    assert adres is None
    assert "PAC" in opis


def test_autowykrywanie_jest_zglaszane(monkeypatch):
    """WPAD to tez sposob na proxy - ale jego nie obslugujemy."""
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {"ProxyEnable": 0, "AutoDetect": 1},
    })
    adres, opis = netproxy._from_registry()
    assert adres is None
    assert "WPAD" in opis


def test_proxy_wlaczony_bez_adresu_daje_brak_proxy(monkeypatch):
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {"ProxyEnable": 1},
    })
    adres, _opis = netproxy._from_registry()
    assert adres is None


# --------------------------------------------------------------------------- #
# raport z rejestru dla diagnostyki
#
# Powstal po tym, jak na komputerze uzytkownika program nie znalazl proxy,
# a nie bylo wiadomo, czy firma go nie ma, czy ma go zapisanego tam, gdzie nie
# patrzymy. Raport odpowiada na to pytanie bez zgadywania.
# --------------------------------------------------------------------------- #
def test_raport_pokazuje_klucz_ktorego_nie_ma(monkeypatch):
    _podstaw_rejestr(monkeypatch, {})
    raport = "\n".join(netproxy.registry_report())
    assert "nie istnieje" in raport


def test_raport_pokazuje_pusty_klucz(monkeypatch):
    """Klucz istnieje, ale nie ma w nim zadnego ustawienia - to inna sytuacja."""
    _podstaw_rejestr(monkeypatch, {("HKCU", SCIECZKA_UZYTKOWNIKA): {}})
    raport = "\n".join(netproxy.registry_report())
    assert "pusty" in raport


def test_raport_wypisuje_wszystkie_wartosci(monkeypatch):
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {
            "ProxyEnable": 1,
            "ProxyServer": "srv01prox.corp:80",
            "ProxyOverride": "<local>",
            "AutoConfigURL": "http://wpad/pac",
            "AutoDetect": 1,
        },
    })
    raport = "\n".join(netproxy.registry_report())

    for nazwa in ("ProxyEnable", "ProxyServer", "ProxyOverride",
                  "AutoConfigURL", "AutoDetect"):
        assert nazwa in raport, f"raport pomija {nazwa}"
    assert "srv01prox.corp:80" in raport


def test_raport_pokazuje_obecnosc_magazynu_winhttp(monkeypatch):
    """Magazyn WinHTTP (netsh winhttp) to osobne miejsce - odnotowujemy go.

    Wlasnie tam firma moze trzymac adres, ktorego nie ma w pozostalych
    kluczach. Nie potrafimy go odczytac, ale diagnostyka ma o nim powiedziec.
    """
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {"ProxyEnable": 1,
                                        "ProxyServer": "srv01prox.corp:80"},
        ("HKCU", SCIECZKA_UZYTKOWNIKA + "\\Connections"):
            {"WinHttpSettings": b"\x00" * 4360},
    })
    raport = "\n".join(netproxy.registry_report())
    assert "WinHttpSettings" in raport
    assert "4360" in raport


def test_raport_na_lindowsie_nie_wybucha(monkeypatch):
    """Bez modulu winreg raport ma powiedziec, ze nie sprawdzal - nie pasc."""
    import sys as _sys
    monkeypatch.setitem(_sys.modules, "winreg", None)
    raport = netproxy.registry_report()
    assert raport and isinstance(raport, list)


# --------------------------------------------------------------------------- #
# ustawienie proxy na czas dzialania programu
# --------------------------------------------------------------------------- #
def test_proxy_z_configu_wygrywa_i_trafia_do_zmiennych(monkeypatch):
    class ZConfigiem(Config):
        PROXY_URL = "proxy.z.configu:8080"

    opis = netproxy.apply(ZConfigiem)

    assert netproxy.current() == "http://proxy.z.configu:8080"
    assert os.environ["HTTPS_PROXY"] == "http://proxy.z.configu:8080"
    assert os.environ["HTTP_PROXY"] == "http://proxy.z.configu:8080"
    assert "config.py" in opis


def test_zmienna_srodowiskowa_jest_szanowana(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://z.zmiennej:8080")
    monkeypatch.setattr(sys, "platform", "win32")

    opis = netproxy.apply(Config)

    assert netproxy.current() == "http://z.zmiennej:8080"
    assert "zmiennej" in opis


def test_proxy_z_rejestru_trafia_do_zmiennych(monkeypatch):
    """Caly mechanizm: odczyt z rejestru -> zmienne srodowiskowe -> httpx."""
    monkeypatch.setattr(sys, "platform", "win32")
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {"ProxyEnable": 1,
                                        "ProxyServer": "srv01prox.corp:80"},
    })

    opis = netproxy.apply(Config)

    assert netproxy.current() == "http://srv01prox.corp:80"
    assert os.environ["HTTPS_PROXY"] == "http://srv01prox.corp:80"
    assert os.environ["HTTP_PROXY"] == "http://srv01prox.corp:80"
    assert "srv01prox" in opis


def test_brak_ustawien_konczy_sie_polaczeniem_bezposrednim(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    _podstaw_rejestr(monkeypatch, {})

    opis = netproxy.apply(Config)

    assert netproxy.current() is None
    assert "HTTPS_PROXY" not in os.environ
    assert "bezposrednie" in opis or "bezpośrednie" in opis


def test_na_linuksie_nie_czytamy_rejestru(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    opis = netproxy.apply(Config)
    assert netproxy.current() is None
    assert opis


def test_apply_nie_wybucha_gdy_config_jest_uszkodzony(monkeypatch):
    class BezPola:
        pass

    monkeypatch.setattr(sys, "platform", "linux")
    opis = netproxy.apply(BezPola)
    assert isinstance(opis, str)


# --------------------------------------------------------------------------- #
# opis dla diagnostyki
# --------------------------------------------------------------------------- #
def test_describe_przed_uzyciem():
    assert isinstance(netproxy.describe(), str)


def test_describe_po_ustaleniu(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {"ProxyEnable": 1,
                                        "ProxyServer": "proxy:8080"},
    })
    netproxy.apply(Config)
    assert "proxy:8080" in netproxy.describe()


# --------------------------------------------------------------------------- #
# komunikaty o bledach
# --------------------------------------------------------------------------- #
def test_komunikat_o_odrzuconym_polaczeniu_wskazuje_proxy(monkeypatch):
    from heic2jpg import telemetry

    monkeypatch.setattr(sys, "platform", "win32")
    _podstaw_rejestr(monkeypatch, {
        ("HKCU", SCIECZKA_UZYTKOWNIKA): {"ProxyEnable": 1,
                                        "ProxyServer": "proxy.firma.pl:8080"},
    })
    netproxy.apply(Config)

    komunikat = telemetry._human_reason(
        RuntimeError("[WinError 10061] odmowa polaczenia"))

    assert "proxy.firma.pl:8080" in komunikat


def test_komunikat_bez_proxy_nie_obwinia_proxy(monkeypatch):
    from heic2jpg import telemetry

    monkeypatch.setattr(sys, "platform", "linux")
    netproxy.apply(Config)

    komunikat = telemetry._human_reason(
        RuntimeError("[WinError 10061] odmowa polaczenia"))

    assert "proxy.firma.pl" not in komunikat
    assert "sieci firmowej" in komunikat


def test_komunikat_o_czasie():
    from heic2jpg import telemetry
    assert "czasie" in telemetry._human_reason(RuntimeError("timed out"))


def test_komunikat_o_dns():
    from heic2jpg import telemetry
    komunikat = telemetry._human_reason(
        RuntimeError("[Errno -2] Name or service not known"))
    assert "adresu" in komunikat


# --------------------------------------------------------------------------- #
# ZAPORA: nie wolno wrocic do dotykania pamieci systemowej
# --------------------------------------------------------------------------- #
def _nazwy_uzyte_w_kodzie(zrodlo: str) -> set:
    """Zwraca nazwy, ktore kod NAPRAWDE uzywa: importy, atrybuty, wywolania.

    Sprawdzamy drzewo skladniowe, a nie tekst - inaczej test lapie wlasne
    opisy oraz nazwy wartosci w rejestrze, ktore sa zwyklymi napisami.
    """
    import ast

    nazwy = set()
    for wezel in ast.walk(ast.parse(zrodlo)):
        if isinstance(wezel, ast.Name):
            nazwy.add(wezel.id)
        elif isinstance(wezel, ast.Attribute):
            nazwy.add(wezel.attr)
        elif isinstance(wezel, ast.Import):
            nazwy.update(alias.name.split(".")[0] for alias in wezel.names)
        elif isinstance(wezel, ast.ImportFrom) and wezel.module:
            nazwy.add(wezel.module.split(".")[0])
    return nazwy


def test_modul_nie_uzywa_ctypes_ani_globalfree():
    """Najwazniejszy test w tym pliku.

    Poprzednia wersja siegala po API WinHTTP przez ctypes i zwalniala pamiec
    funkcja GlobalFree. Pomylka w zwalnianiu zakonczyla sie uszkodzeniem
    sterty i natychmiastowa smiercia programu (0xc0000374) - bez komunikatu,
    bez logu, bez mozliwosci zdiagnozowania.

    Ustalanie adresu proxy to czytanie kilku wartosci z rejestru. Wskazniki sa
    tu zbedne, a ich obecnosc oznacza, ze ktos znowu wprowadza to ryzyko.
    """
    nazwy = _nazwy_uzyte_w_kodzie(
        open(netproxy.__file__, encoding="utf-8").read())

    zakazane = {
        "ctypes", "Windll", "windll", "WinDLL",
        "GlobalFree", "WinHttpOpen", "WinHttpCloseHandle",
        "WinHttpGetProxyForUrl", "WinHttpGetIEProxyConfigForCurrentUser",
        "Structure", "POINTER", "byref", "cast", "c_void_p", "c_wchar_p",
    }
    uzyte = zakazane & nazwy
    assert not uzyte, (
        f"kod modulu netproxy uzywa {sorted(uzyte)}. Ustalanie proxy ma nie "
        "dotykac pamieci systemowej - patrz opis tego testu."
    )


def test_nie_ma_zbednych_struktur_w_module():
    for nazwa in ("ProxyConfig", "AutoProxyOptions", "ProxyInfo",
                  "_from_windows", "detect"):
        assert not hasattr(netproxy, nazwa), (
            f"modul netproxy nadal ma '{nazwa}' - to pozostalosc po starym, "
            "niebezpiecznym podejsciu"
        )
