"""Wykrywanie serwera proxy - bez dotykania pamieci systemowej.

ZASADA DZIALANIA (celowo najprostsza z mozliwych)
-------------------------------------------------
Program ustala adres proxy i wpisuje go do zmiennych srodowiskowych procesu
(HTTPS_PROXY, HTTP_PROXY). Biblioteka httpx czyta je samodzielnie - nic wiecej
nie trzeba zrobic ani jej przekazywac. Ustawienie zyje tak dlugo, jak proces.

Kolejnosc, od najmocniejszego:
  1. PROXY_URL z config.py      - reczne ustawienie, zawsze wygrywa
  2. zmienne srodowiskowe       - uzytkownik juz je ustawil, nie ruszamy
  3. rejestr Windows (winreg)   - ustawienia uzytkownika i zasady firmowe

DLACZEGO NIE PRZEZ API SYSTEMOWE
---------------------------------
Poprzednia wersja pytala system przez API WinHTTP: ctypes, wlasne struktury
i zwalnianie pamieci przez GlobalFree. Bylo to zbedne i niebezpieczne.
Pomylka w zwalnianiu pamieci konczy sie uszkodzeniem sterty, a Windows
przerywa wtedy proces NATYCHMIAST - z kodem 0xc0000374, bez komunikatu
i bez mozliwosci przechwycenia bledu. Program ginie, zanim zdazy cokolwiek
zapisac, wiec nawet nie ma jak tego zdiagnozowac.

Wniosek: czytanie dwoch wartosci z rejestru zalatwia sprawe. Sieganie po
wskazniki jest tu nie tylko zbedne - jest wrecz szkodliwe.

CZEGO NIE OBSLUGUJEMY
---------------------
Plik PAC (AutoConfigURL). Zeby go rozwiazac, system musi wykonac skrypt
wyliczajacy adres - bez wywolywania kodu systemowego nie da sie tego zrobic.
Jesli PAC jest ustawiony, a nie ma wpisanego serwera, program laczy sie
bezposrednio i zapisuje to w diagnostyce.
"""
from __future__ import annotations

import os
import sys

# Zmienne, ktorych uzywa httpx. Jezeli ktoras jest ustawiona, uzytkownik
# zrobil to swiadomie i nie nadpisujemy jej.
ENV_VARIABLES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
                 "ALL_PROXY", "all_proxy")

# Co mowimy o pliku PAC, gdy go znajdziemy.
PAC_NOTE = "ustawiony plik PAC (AutoConfigURL) - jego nie odczytamy"

# Wartosci w rejestrze, ktore moga opisac ustawienie proxy.
# ProxyEnable=1 wlacza serwer, AutoDetect=1 wlacza wykrywanie automatyczne.
WARTOSCI_PROXY = ("ProxyEnable", "ProxyServer", "ProxyOverride",
                  "AutoConfigURL", "AutoDetect")

# Osobny magazyn WinHTTP (ten, ktory pokazuje `netsh winhttp show proxy`).
# Lezy w podkluczu Connections jako dane binarne o nieudokumentowanym
# formacie - nie odczytujemy go, ale odnotowujemy w diagnostyce.
PODKLUCZ_POLACZEN = "Connections"
WARTOSC_WINHTTP = "WinHttpSettings"

# Wynik ostatniego ustalenia - zeby diagnostyka i komunikaty o bledach
# mogly powiedziec, co program faktycznie zrobil.
_ustawione: str | None = None
_zrodlo: str = "nie sprawdzano"


# --------------------------------------------------------------------------- #
# ustawienie proxy na czas dzialania programu
# --------------------------------------------------------------------------- #
def apply(config) -> str:
    """Ustala proxy i wpisuje je do zmiennych srodowiskowych procesu.

    Wywolywane raz, na starcie. Zwraca opis dla diagnostyki.
    """
    global _ustawione, _zrodlo

    # 1. Ustawienie reczne z config.py.
    reczne = (getattr(config, "PROXY_URL", "") or "").strip()
    if reczne:
        _ustawione = reczne if "://" in reczne else f"http://{reczne}"
        _zrodlo = "z config.py (PROXY_URL)"
        ustaw_zmienne(_ustawione)
        return f"{_zrodlo}: {_ustawione}"

    # 2. Zmienne srodowiskowe - uzytkownik juz je ustawil.
    z_zmiennej = env_proxy()
    if z_zmiennej:
        _ustawione, _zrodlo = z_zmiennej, "ze zmiennej srodowiskowej"
        return f"{_zrodlo}: {z_zmiennej}"

    # 3. Rejestr Windows.
    if sys.platform.startswith("win"):
        znalezione = _from_registry()
        if znalezione is not None:
            adres, opis = znalezione
            if adres:
                _ustawione, _zrodlo = adres, f"z {opis}"
                ustaw_zmienne(adres)
                return f"{_zrodlo}: {adres}"
            _ustawione, _zrodlo = None, opis
            return opis

    _ustawione, _zrodlo = None, "nie znaleziono (polaczenie bezposrednie)"
    return _zrodlo


def ustaw_zmienne(adres: str) -> None:
    """Wpisuje adres do zmiennych srodowiskowych procesu."""
    for nazwa in ("HTTPS_PROXY", "HTTP_PROXY"):
        os.environ[nazwa] = adres


def current() -> str | None:
    """Adres proxy ustawiony dla tego procesu (albo None)."""
    return _ustawione


def describe() -> str:
    """Opis dla trybu --diagnostic."""
    if _ustawione:
        return f"{_zrodlo}: {_ustawione}"
    return _zrodlo


def env_proxy() -> str | None:
    """Proxy ustawione zmienna srodowiskowa, jesli jakas jest."""
    for nazwa in ENV_VARIABLES:
        wartosc = (os.environ.get(nazwa) or "").strip()
        if wartosc:
            return wartosc if "://" in wartosc else f"http://{wartosc}"
    return None


# --------------------------------------------------------------------------- #
# rejestr Windows
# --------------------------------------------------------------------------- #
def _lokalizacje(winreg):
    """Gdzie Windows trzyma ustawienia proxy. Kolejnosc = priorytet."""
    return [
        (winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
         "ustawienia uzytkownika"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Policies\Microsoft\Windows\CurrentVersion\Internet Settings",
         "zasady firmowe"),
    ]


def _from_registry():
    """Czyta proxy z rejestru. Zwraca (adres_albo_None, opis) albo None.

    None znaczy "nie ma czego szukac na tej platformie".
    Drugi element opisuje, co znaleziono - takze wtedy, gdy to PAC, ktorego
    nie potrafimy odczytac.
    """
    try:
        import winreg
    except ImportError:      # nie Windows
        return None

    znaleziony_pac = False
    wlaczone_autowykrywanie = False

    for galaz, sciezka, opis in _lokalizacje(winreg):
        dane = _czytaj_wartosci(winreg, galaz, sciezka)
        if not dane:
            continue

        if dane.get("AutoConfigURL"):
            znaleziony_pac = True
        if int(dane.get("AutoDetect") or 0) == 1:
            wlaczone_autowykrywanie = True

        if int(dane.get("ProxyEnable") or 0) == 1 and dane.get("ProxyServer"):
            adres = _clean_proxy(str(dane["ProxyServer"]))
            if adres:
                return adres, opis

    if znaleziony_pac:
        return None, PAC_NOTE
    if wlaczone_autowykrywanie:
        return None, ("wlaczone automatyczne wykrywanie (WPAD) - "
                      "tego nie obslugujemy")
    return None, "brak ustawien proxy w rejestrze (polaczenie bezposrednie)"


def _czytaj_wartosci(winreg, galaz, sciezka):
    """Zwraca slownik ustawien proxy pod danym kluczem.

    None = klucza nie ma w ogole. Pusty slownik = klucz jest, ale nic w nim
    nie ustawiono. To rozroznienie jest wazne dla diagnostyki.
    """
    try:
        with winreg.OpenKey(galaz, sciezka) as klucz:
            dane = {}
            for nazwa in WARTOSCI_PROXY:
                wartosc, _typ = _pobierz(winreg, klucz, nazwa)
                if wartosc is not None:
                    dane[nazwa] = wartosc

            # Magazyn WinHTTP lezy w podkluczu Connections i jest danymi
            # binarnymi o nieudokumentowanym formacie. Nie odczytujemy go, ale
            # sama jego obecnosc jest cenna wskazowka w diagnostyce.
            try:
                with winreg.OpenKey(klucz, PODKLUCZ_POLACZEN) as podklucz:
                    blob, _typ = _pobierz(winreg, podklucz, WARTOSC_WINHTTP)
                    if blob:
                        dane[WARTOSC_WINHTTP] = (
                            len(blob) if isinstance(blob, (bytes, bytearray))
                            else None)
            except OSError:
                pass

            return dane
    except OSError:
        return None


def registry_report() -> list[str]:
    """Pelny raport z rejestru - dla trybu --diagnostic.

    Wypisuje KAZDE sprawdzone miejsce i kazda wartosc, ktora moze opisac
    ustawienie proxy. Bez tego nie da sie odroznic trzech roznych sytuacji:
    "firma nie ma proxy", "firma ma proxy, ale zapisane gdzie indziej"
    oraz "firma uzywa pliku PAC albo wykrywania automatycznego".
    """
    try:
        import winreg
    except ImportError:
        return ["  (system inny niz Windows - rejestru nie sprawdzamy)"]

    linie = []
    for galaz, sciezka, opis in _lokalizacje(winreg):
        nazwa = "HKCU" if galaz == winreg.HKEY_CURRENT_USER else "HKLM"
        dane = _czytaj_wartosci(winreg, galaz, sciezka)

        if dane is None:
            linie.append(f"  {opis} ({nazwa}): klucz nie istnieje")
            continue
        if not dane:
            linie.append(f"  {opis} ({nazwa}): klucz jest, ale pusty")
            continue

        linie.append(f"  {opis} ({nazwa}):")
        for nazwa_wartosci in WARTOSCI_PROXY:
            if nazwa_wartosci in dane:
                linie.append(f"      {nazwa_wartosci:<15}= {dane[nazwa_wartosci]}")
        if WARTOSC_WINHTTP in dane:
            rozmiar = dane[WARTOSC_WINHTTP]
            opis_rozmiaru = f" ({rozmiar} B, nie odczytujemy)" if rozmiar else ""
            linie.append(f"      {WARTOSC_WINHTTP:<15}= obecny{opis_rozmiaru}")

    return linie


def _pobierz(winreg, klucz, nazwa):
    try:
        return winreg.QueryValueEx(klucz, nazwa)
    except OSError:
        return None, None


# --------------------------------------------------------------------------- #
# normalizacja
# --------------------------------------------------------------------------- #
def _clean_proxy(raw: str, scheme: str = "https") -> str:
    """Zamienia to, co zwraca system, na adres zrozumialy dla httpx.

    System potrafi zwrocic:
      - "proxy:8080"                          jedno ustawienie dla wszystkiego
      - "http=proxy:80;https=proxy:443"       osobno dla kazdego protokolu
      - "proxy1:80;proxy2:80"                 kilka serwerow po kolei
      - "DIRECT"                              bezposrednie polaczenie
    """
    if not raw:
        return ""

    wartosc = raw.strip()
    if not wartosc or wartosc.upper() == "DIRECT":
        return ""

    # Wpisy dla poszczegolnych protokolow.
    if "=" in wartosc:
        wpisy = {}
        for element in wartosc.split(";"):
            if "=" in element:
                protokol, _, adres = element.partition("=")
                wpisy[protokol.strip().lower()] = adres.strip()
        wartosc = wpisy.get(scheme) or wpisy.get("http") or ""
        if not wartosc:
            return ""

    # Kilka serwerow - bierzemy pierwszy sensowny.
    if ";" in wartosc:
        for element in wartosc.split(";"):
            element = element.strip()
            if element and element.upper() != "DIRECT":
                wartosc = element
                break
        else:
            return ""

    wartosc = wartosc.strip()
    if not wartosc:
        return ""
    return wartosc if "://" in wartosc else f"http://{wartosc}"
