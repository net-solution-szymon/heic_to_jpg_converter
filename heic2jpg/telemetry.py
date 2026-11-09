"""Anonymous statistics and the "message the developer" transport.

WHAT IS SENT
------------
A random installation identifier, the program version, the operating system,
and the total number of converted files. That is the whole payload.

WHAT IS NEVER SENT
------------------
File names, folder paths, image contents, the Windows user name, or any
hardware identifier (disk serial, MAC address, motherboard UUID). Counting
*installations* is enough for statistics, and it keeps the program on the
right side of data protection rules: no hardware fingerprint is collected.

The identifier is a random UUID generated on first run and stored in the
user's data folder. It is not derived from anything about the machine, so it
cannot be used to identify a person, and deleting the data file resets it.
The user can switch reporting off in Pomoc -> Prywatnosc; when it is off, no
connection is made at all.
"""
from __future__ import annotations

import platform
import threading
import uuid
from datetime import datetime, timezone

from . import store

USER_AGENT = "heic2jpg-telemetry"


# --------------------------------------------------------------------------- #
# identity and consent
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    """UTC timestamp, seconds precision - no local time, no timezone leak."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_identity(values: dict) -> dict:
    """Give this installation an identifier and a first-seen date, once."""
    changed = False
    if not values.get(store.KEY_INSTALL_ID):
        values[store.KEY_INSTALL_ID] = str(uuid.uuid4())
        changed = True
    if not values.get(store.KEY_FIRST_SEEN):
        values[store.KEY_FIRST_SEEN] = now_iso()
        changed = True
    if changed:
        store.save(values)
    return values


def enabled(values: dict) -> bool:
    """Is the user OK with anonymous statistics?"""
    return bool(values.get(store.KEY_TELEMETRY, True))


def set_enabled(values: dict, allowed: bool) -> dict:
    return store.set_value(values, store.KEY_TELEMETRY, bool(allowed))


def _due(values: dict, every_hours: int) -> bool:
    """Has enough time passed since the last report?"""
    last = values.get(store.KEY_LAST_PING) or ""
    if not last:
        return True
    try:
        previous = datetime.fromisoformat(last)
    except ValueError:
        return True
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - previous).total_seconds()
    return elapsed >= every_hours * 3600


# --------------------------------------------------------------------------- #
# payloads
# --------------------------------------------------------------------------- #
def statistics_payload(values: dict, config) -> dict:
    return {
        "install_id": values.get(store.KEY_INSTALL_ID, ""),
        "version": getattr(config, "APP_VERSION", ""),
        "os": platform.system().lower(),
        "os_release": platform.release(),
        "converted_total": int(values.get(store.KEY_CONVERTED_TOTAL, 0)),
        "first_seen": values.get(store.KEY_FIRST_SEEN, ""),
    }


def diagnostics_text(values: dict, config) -> str:
    """Human-readable block attached to a message when the user ticks the box.

    Deliberately the same information as the ping - it exists so a bug report
    is actionable, not so we can profile anybody.
    """
    return "\n".join([
        f"Program: {getattr(config, 'APP_NAME', 'HEIC2JPG')} "
        f"{getattr(config, 'APP_VERSION', '?')}",
        f"System: {platform.system()} {platform.release()} ({platform.machine()})",
        f"Python: {platform.python_version()}",
        f"Konwersji łącznie: {int(values.get(store.KEY_CONVERTED_TOTAL, 0))}",
        f"Pierwsze uruchomienie: {values.get(store.KEY_FIRST_SEEN, '?')}",
    ])


# --------------------------------------------------------------------------- #
# transport
# --------------------------------------------------------------------------- #
def _kontakt(config) -> str:
    """Dopisek z adresem kontaktowym - ostatnia droga dla uzytkownika.

    Gdy wysylka przez siec sie nie uda, uzytkownik nie moze zostac bez
    sposobu, zeby sie z nami skontaktowac.
    """
    adres = (getattr(config, "SUPPORT_EMAIL", "") or "").strip() if config else ""
    if adres:
        return f" Możesz też napisać do mnie bezpośrednio na adres {adres}."
    return ""


def _human_reason(exc: Exception, config=None) -> str:
    """Zamienia blad sieci na zdanie, ktore cos znaczy dla uzytkownika.

    Surowy komunikat w rodzaju "ProxyError: 407" nie mowi czlowiekowi nic.
    A najczestsza przyczyna w firmach jest proxy wymagajace zalogowania -
    tego program nie obsluzy, wiec uzytkownik musi wiedziec, co sie stalo
    i ze ma inna droge kontaktu.
    """
    tekst = f"{type(exc).__name__}: {exc}"
    niski = tekst.lower()
    kontakt = _kontakt(config)

    if "407" in tekst or "proxy authentication required" in niski:
        return ("Serwer proxy w Twojej sieci wymaga zalogowania, a program nie "
                "ma Twoich danych logowania. Spróbuj połączyć się bez VPN, "
                "czyli bez firmowego proxy." + kontakt)

    if "proxyerror" in niski or "proxy" in niski and "connect" in niski:
        return ("Nie udało się połączyć przez serwer proxy Twojej sieci. "
                "Spróbuj bez VPN, czyli bez firmowego proxy." + kontakt)

    if "10061" in tekst or "connection refused" in niski or "errno 111" in niski:
        return ("Połączenie zostało odrzucone przez sieć. Jeśli pracujesz "
                "w sieci firmowej lub przez VPN, spróbuj bez VPN - firmowe "
                "proxy może blokować ten adres." + kontakt)

    if "10060" in tekst or "timed out" in niski or "timeout" in niski:
        return ("Serwer nie odpowiedział w wyznaczonym czasie. "
                "Sprawdź połączenie z internetem." + kontakt)

    if ("getaddrinfo" in niski or "name or service not known" in niski
            or "11001" in tekst):
        return ("Nie udało się odnaleźć adresu serwera. "
                "Sprawdź połączenie z internetem." + kontakt)

    if "certificate" in niski or "ssl" in niski:
        return ("Problem z certyfikatem połączenia. W sieci firmowej może być "
                "wymagany firmowy certyfikat." + kontakt)

    return f"Nie udało się połączyć z serwerem. Szczegóły: {tekst}" + kontakt


def _post(config, path: str, payload: dict, timeout: float | None = None):
    """POST JSON i zwrot (ok, komunikat). Nigdy nie zglasza wyjatku.

    Kazda awaria jest polykana celowo: statystyki sa funkcja dodatkowa i nie
    moga pokazywac okien z bledami.
    """
    base = (getattr(config, "SERVER_URL", "") or "").rstrip("/")
    if not base:
        return False, "brak adresu serwera"

    try:
        import httpx
    except ImportError:
        return False, "brak biblioteki httpx"

    limit = timeout if timeout is not None else getattr(config, "TELEMETRY_TIMEOUT", 6.0)
    url = base + path

    # Bez proxy i bez zadnych ustawien sieciowych: httpx laczy sie tak, jak
    # system mu pozwala. Gdy sie nie uda, uzytkownik dostaje powod (patrz
    # _human_reason) - w tym informacje, ze winne moze byc firmowe proxy.
    try:
        response = httpx.post(url, json=payload, timeout=limit,
                              headers={"User-Agent": USER_AGENT})
        if response.status_code not in (200, 201):
            return False, f"serwer odpowiedział {response.status_code}"
        return True, ""
    except Exception as exc:  # noqa: BLE001 - offline, DNS, TLS, cokolwiek
        return False, _human_reason(exc, config)


def send_statistics(values: dict, config) -> tuple[bool, str]:
    """Report the counters. Updates last_ping only on success."""
    ok, message = _post(config, "/api/v1/ping", statistics_payload(values, config))
    if ok:
        store.set_value(values, store.KEY_LAST_PING, now_iso())
    return ok, message


def send_message(values: dict, config, text: str, contact: str = "",
                 include_diagnostics: bool = True) -> tuple[bool, str]:
    """Send a user message. Unlike telemetry this reports failures - the user
    pressed a button and deserves to know whether it arrived."""
    payload = {
        "message": text,
        "contact": contact,
        "version": getattr(config, "APP_VERSION", ""),
        "os": platform.system().lower(),
    }
    if include_diagnostics:
        payload["diagnostics"] = diagnostics_text(values, config)
    return _post(config, "/api/v1/message", payload)


def send_statistics_in_background(values: dict, config) -> None:
    """Fire the report from a daemon thread so the UI never waits on it."""
    if not enabled(values):
        return
    if not _due(values, getattr(config, "TELEMETRY_INTERVAL_HOURS", 24)):
        return
    threading.Thread(
        target=send_statistics, args=(values, config),
        name="telemetry-ping", daemon=True,
    ).start()
