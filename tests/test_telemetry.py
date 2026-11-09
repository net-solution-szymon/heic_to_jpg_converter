"""Testy anonimowych statystyk.

Dwa cele:
  1. wysylka ma byc cicha, rzadka i wylaczalna,
  2. do serwera NIE MOGA trafic dane, ktorych obiecalismy nie wysylac.

Drugi punkt jest sprawdzany doslownie - test porownuje liste pol zgloszenia
z czarna lista nazw, ktore nie moga sie tam pojawic.
"""
from datetime import datetime, timedelta, timezone

import config
from heic2jpg import store, telemetry


def _values(**overrides):
    values = dict(store.DEFAULTS)
    values.update(overrides)
    return values


# --------------------------------------------------------------------------- #
# tozsamosc instalacji
# --------------------------------------------------------------------------- #
def test_identity_is_created_once_and_reused(isolated_data):
    values = _values()
    telemetry.ensure_identity(values)
    first = values[store.KEY_INSTALL_ID]
    assert first
    assert values[store.KEY_FIRST_SEEN]

    telemetry.ensure_identity(values)
    assert values[store.KEY_INSTALL_ID] == first, \
        "ponowne uruchomienie nie moze tworzyc nowej instalacji"


def test_identity_survives_a_restart(isolated_data):
    values = _values()
    telemetry.ensure_identity(values)
    stored = store.load()
    assert stored[store.KEY_INSTALL_ID] == values[store.KEY_INSTALL_ID]


def test_identity_is_not_derived_from_the_machine(isolated_data):
    """Identyfikator to losowy UUID - nie zawiera niczego o komputerze."""
    values = _values()
    telemetry.ensure_identity(values)
    identifier = values[store.KEY_INSTALL_ID]

    import platform
    import socket
    import uuid

    # Musi byc poprawnym UUID...
    assert uuid.UUID(identifier)
    # ...i nie moze zawierac nazwy komputera ani uzytkownika.
    blob = f"{platform.node()} {socket.gethostname()}".lower()
    for token in blob.split():
        if len(token) > 3:
            assert token not in identifier.lower()


# --------------------------------------------------------------------------- #
# tresc zgloszenia
# --------------------------------------------------------------------------- #
def test_payload_has_exactly_the_expected_fields(isolated_data):
    values = _values()
    telemetry.ensure_identity(values)
    payload = telemetry.statistics_payload(values, config)
    assert set(payload) == {
        "install_id", "version", "os", "os_release",
        "converted_total", "first_seen",
    }


def test_payload_contains_nothing_personal(isolated_data):
    """Sprawdzenie obietnicy z okna 'Prywatnosc', slowo w slowo."""
    values = _values()
    values[store.KEY_CONVERTED_TOTAL] = 12
    telemetry.ensure_identity(values)

    blob = str(telemetry.statistics_payload(values, config)).lower()
    forbidden = [
        "hwid", "mac", "disk", "serial", "uuid_płyty", "motherboard",
        "hostname", "username", "user_name", "path", "folder", "file",
        "image", "photo", "email",
    ]
    for word in forbidden:
        assert word not in blob, f"zgloszenie zawiera niedozwolone dane: {word}"


def test_diagnostics_text_has_no_file_or_user_data(isolated_data):
    values = _values()
    telemetry.ensure_identity(values)
    text = telemetry.diagnostics_text(values, config).lower()
    assert "@" not in text          # zadnego adresu e-mail
    assert "\\users\\" not in text  # zadnej sciezki Windows
    assert "/home/" not in text


# --------------------------------------------------------------------------- #
# zgoda i czestotliwosc
# --------------------------------------------------------------------------- #
def test_enabled_by_default(isolated_data):
    assert telemetry.enabled(_values()) is True


def test_opt_out_is_remembered(isolated_data):
    values = _values()
    telemetry.set_enabled(values, False)
    assert telemetry.enabled(store.load()) is False


def test_disabled_means_no_connection_at_all(isolated_data, monkeypatch):
    """Po wylaczeniu statystyk program nie moze nawet probowac sie laczyc."""
    values = _values(**{store.KEY_TELEMETRY: False})

    def boom(*_a, **_k):  # pragma: no cover - nie powinno byc wolane
        raise AssertionError("wyslano zgloszenie mimo wylaczonych statystyk")

    monkeypatch.setattr(telemetry, "_post", boom)
    telemetry.send_statistics_in_background(values, config)


def test_first_run_is_due_immediately(isolated_data):
    assert telemetry._due(_values(), 24) is True


def test_recent_report_is_not_due_again(isolated_data):
    values = _values()
    values[store.KEY_LAST_PING] = datetime.now(timezone.utc).replace(
        microsecond=0).isoformat()
    assert telemetry._due(values, 24) is False


def test_old_report_becomes_due(isolated_data):
    values = _values()
    old = datetime.now(timezone.utc) - timedelta(hours=25)
    values[store.KEY_LAST_PING] = old.replace(microsecond=0).isoformat()
    assert telemetry._due(values, 24) is True


def test_broken_timestamp_does_not_block_reporting(isolated_data):
    values = _values()
    values[store.KEY_LAST_PING] = "wczoraj"
    assert telemetry._due(values, 24) is True


# --------------------------------------------------------------------------- #
# transport
# --------------------------------------------------------------------------- #
def test_successful_report_records_the_time(isolated_data, monkeypatch):
    values = _values()
    monkeypatch.setattr(telemetry, "_post", lambda *a, **k: (True, ""))
    ok, _ = telemetry.send_statistics(values, config)
    assert ok is True
    assert values[store.KEY_LAST_PING]


def test_failed_report_does_not_record_the_time(isolated_data, monkeypatch):
    """Jesli wysylka sie nie udala, nastepne uruchomienie ma sprobowac znowu."""
    values = _values()
    monkeypatch.setattr(telemetry, "_post", lambda *a, **k: (False, "brak sieci"))
    ok, error = telemetry.send_statistics(values, config)
    assert ok is False
    assert error == "brak sieci"
    assert values[store.KEY_LAST_PING] == ""


def test_no_server_url_means_no_request(isolated_data, monkeypatch):
    class Cfg:
        SERVER_URL = ""
        TELEMETRY_TIMEOUT = 1

    def boom(*_a, **_k):  # pragma: no cover
        raise AssertionError("proba polaczenia bez adresu serwera")

    monkeypatch.setattr("httpx.post", boom)
    ok, error = telemetry._post(Cfg, "/api/v1/ping", {})
    assert ok is False
    assert "adres" in error


def test_client_never_raises_on_network_failure(isolated_data, monkeypatch):
    """Awaria sieci nie moze wywalic programu ani pokazac bledu uzytkownikowi."""
    def broken(*_a, **_k):
        raise OSError("brak sieci")

    values = _values()
    values[store.KEY_INSTALL_ID] = "abc"
    monkeypatch.setattr("httpx.post", broken)

    ok, error = telemetry.send_statistics(values, config)
    assert ok is False
    assert "OSError" in error


# --------------------------------------------------------------------------- #
# komunikaty o nieudanej wysylce
#
# To jedyne, co uzytkownik zobaczy, gdy wiadomosc nie dojdzie. Musi wiec
# powiedziec DWIE rzeczy: co sie stalo i co moze zrobic. W sieci firmowej
# najczestsza przyczyna jest proxy wymagajace zalogowania - tego programu nie
# obsluguje, wiec uzytkownik ma sprobowac bez VPN albo napisac na maila.
# --------------------------------------------------------------------------- #
class _Config:
    SUPPORT_EMAIL = "pomoc@przyklad.pl"


class _BezMaila:
    SUPPORT_EMAIL = ""


def test_proxy_wymagajacy_logowania_mowi_o_vpn_i_o_mailu():
    class ProxyError(Exception):
        pass

    komunikat = telemetry._human_reason(
        ProxyError("407 Proxy Authentication Required"), _Config)

    assert "logowania" in komunikat
    assert "VPN" in komunikat
    assert "pomoc@przyklad.pl" in komunikat


def test_blad_proxy_mowi_o_vpn():
    class ProxyError(Exception):
        pass

    komunikat = telemetry._human_reason(
        ProxyError("Cannot connect to proxy"), _Config)

    assert "proxy" in komunikat.lower()
    assert "VPN" in komunikat
    assert "pomoc@przyklad.pl" in komunikat


def test_odrzucone_polaczenie_mowi_o_vpn():
    komunikat = telemetry._human_reason(
        RuntimeError("[WinError 10061] connection refused"), _Config)

    assert "VPN" in komunikat
    assert "pomoc@przyklad.pl" in komunikat


def test_przekroczony_czas_mowi_o_czasie():
    komunikat = telemetry._human_reason(RuntimeError("timed out"), _Config)
    assert "czasie" in komunikat
    assert "pomoc@przyklad.pl" in komunikat


def test_brak_dns_mowi_o_adresie():
    komunikat = telemetry._human_reason(
        RuntimeError("[Errno -2] Name or service not known"), _Config)
    assert "adresu" in komunikat


def test_bez_adresu_kontaktowego_nie_ma_zwisu():
    """Gdy wlasciciel nie podal maila, zdanie o pisaniu nie moze sie pojawic."""
    komunikat = telemetry._human_reason(RuntimeError("timed out"), _BezMaila)
    assert "napisz" not in komunikat.lower()
    assert komunikat.endswith("internetem.")


def test_komunikat_zawsze_cos_mowi():
    """Takze dla bledu, ktorego nie przewidzielismy."""
    komunikat = telemetry._human_reason(RuntimeError("cos dziwnego"), _Config)
    assert komunikat
    assert "cos dziwnego" in komunikat
    assert "pomoc@przyklad.pl" in komunikat


def test_komunikat_bez_configu_nie_wybucha():
    """Wywolanie bez konfiguracji tez musi dac sensowne zdanie."""
    komunikat = telemetry._human_reason(RuntimeError("timed out"))
    assert komunikat and "czasie" in komunikat
