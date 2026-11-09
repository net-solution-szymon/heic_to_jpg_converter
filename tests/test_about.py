"""Testy okien informacyjnych i tresci, ktore one pokazuja.

Same okna sa sprawdzane w testach interfejsu; tutaj chodzi o TRESC:
licencja musi byc czytelna, link do repozytorium musi sie podstawic,
a informacja o prywatnosci musi mowic prawde o tym, co program wysyla.
"""
import config
from heic2jpg import about, store, telemetry


def _values(**overrides):
    values = dict(store.DEFAULTS)
    values.update(overrides)
    return values


# --------------------------------------------------------------------------- #
# pliki z trescia
# --------------------------------------------------------------------------- #
def test_licence_file_is_readable(isolated_data):
    text = about.legal_text("EULA-HEIC-to-JPG-Converter.txt")
    assert "UMOWA LICENCYJNA" in text
    assert len(text) > 2000, "licencja nie powinna byc skrocona"


def test_third_party_notices_are_readable(isolated_data):
    text = about.legal_text("THIRD-PARTY-NOTICES.txt")
    assert len(text) > 2000
    # Noty musza wymienic biblioteki, ktore faktycznie sa w programie.
    for name in ("pillow", "heif", "customtkinter", "tkinterdnd2"):
        assert name.lower() in text.lower(), f"brak informacji o {name}"


def test_missing_file_gives_a_readable_message_not_an_exception(isolated_data):
    text = about.legal_text("nie-ma-takiego-pliku.txt")
    assert "Nie mogę odczytać" in text


def test_licence_has_no_unfilled_placeholders(isolated_data):
    """W wydanej umowie nie moze zostac ani jedno pole w nawiasach.

    Regresja: umowa wychodzila z polami typu [NIP] czy [ADRES REPOZYTORIUM],
    ktore uzytkownik widzial w oknie "Licencja". Braki musza byc wychwycone
    przed wydaniem, a nie po.
    """
    import re

    text = about.licence_text()
    pola = sorted(set(re.findall(r"\[[^\]]{2,60}\]", text)))
    assert pola == [], f"nieuzupelnione pola w umowie: {pola}"


def test_licence_has_the_author_data(isolated_data):
    """Umowa musi wskazywac autora i droge kontaktu - inaczej jest bezwartosciowa."""
    text = about.licence_text()
    for oczekiwane in (
        "Szymon Jankojć",
        "szymon.jankojc@net-solution.pl",
        "https://github.com/net-solution-szymon/heic_to_jpg_converter",
        "https://heictojpg.net-solution.pl",
    ):
        assert oczekiwane in text, f"brak w umowie: {oczekiwane}"


def test_licence_email_is_written_the_same_everywhere(isolated_data):
    """Jeden adres zapisany raz wielka, raz mala litera to proszenie sie o blad."""
    import re

    text = about.licence_text()
    adresy = set(re.findall(r"\S*@net-solution\.pl", text))
    assert adresy == {"szymon.jankojc@net-solution.pl"}, (
        f"adres kontaktowy wystepuje w roznych postaciach: {adresy}")


def test_licence_has_no_leftover_section_from_the_paid_version(isolated_data):
    text = about.licence_text().lower()
    for fraza in ("warunki korzystania z klucza licencyjnego",
                  "wymaga aktywacji przy użyciu",
                  "cennik licencjodawcy",
                  "odcisk urządzenia"):
        assert fraza not in text, f"EULA nadal zawiera zapis z wersji platnej: {fraza!r}"


def test_licence_matches_the_free_model(isolated_data):
    """Umowa nie moze obiecywac klucza, aktywacji ani oplac - bo ich nie ma.

    Regresja: pierwotna wersja byla napisana pod sprzedaz subskrypcji i mowila
    o kluczu licencyjnym, weryfikacji na serwerze i zwrotach za oplate. W
    darmowym programie takie zapisy sa po prostu nieprawdziwe.
    """
    text = about.licence_text().lower()

    nieaktualne = [
        "warunki korzystania z klucza licencyjnego",
        "wymaga aktywacji przy użyciu",
        "zablokowania klucza licencyjnego",
        "cennik licencjodawcy",
        "uiszczonej opłaty na zasadach",
        "odcisk urządzenia",
        "identyfikator urządzenia wyliczony z jego parametrów",
        "pyjwt",
        "cryptography",
    ]
    for phrase in nieaktualne:
        assert phrase not in text, f"EULA nadal zawiera zapis z wersji platnej: {phrase!r}"

    # ...i musi mowic o tym, co jest prawda.
    for phrase in ("bezpłatnie", "bezterminowo", "dobrowolnie",
                   "anonimowe statystyki"):
        assert phrase in text, f"EULA nie mowi o: {phrase!r}"


# --------------------------------------------------------------------------- #
# tresci okien
# --------------------------------------------------------------------------- #
def test_about_text_contains_version_and_counters(isolated_data):
    values = _values(**{store.KEY_CONVERTED_TOTAL: 321, store.KEY_SESSIONS: 9})
    text = about.about_text(config, values)
    assert config.APP_VERSION in text
    assert "321" in text
    assert "9" in text


def test_about_text_mentions_telemetry_honestly(isolated_data):
    text = about.about_text(config, _values()).lower()
    assert "anonimowe" in text
    assert "nie zbiera" in text


def test_privacy_text_lists_what_is_sent(isolated_data):
    telemetry.ensure_identity(_values())
    values = _values()
    text = about.privacy_text(config, values)
    for expected in ("identyfikator instalacji", "wersję programu",
                     "liczbę przekonwertowanych plików"):
        assert expected in text
    for forbidden in ("nazw ani zawartości zdjęć", "identyfikatora sprzętu",
                      "Adresy IP nie są zapisywane"):
        assert forbidden in text


def test_privacy_text_shows_the_current_switch_state(isolated_data):
    values = _values()
    assert "WŁĄCZONE" in about.privacy_text(config, values)

    telemetry.set_enabled(values, False)
    assert "WYŁĄCZONE" in about.privacy_text(config, values)


def test_privacy_text_shows_the_identifier_and_file(isolated_data):
    values = _values()
    telemetry.ensure_identity(values)
    text = about.privacy_text(config, values)
    assert values[store.KEY_INSTALL_ID] in text
    assert str(store.data_file()) in text
