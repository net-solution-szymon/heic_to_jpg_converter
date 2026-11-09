"""Testy prosby o wsparcie.

Sedno: prosba ma sie pojawiac rzadko, po realnej korzysci, i musi uszanowac
kazda decyzje uzytkownika. Te testy pilnuja wlasnie tego - latwo tu o blad,
ktory zamienia darmowy program w natretny.
"""
from datetime import datetime, timedelta, timezone

import config
from heic2jpg import store, support


def _values(**overrides):
    values = dict(store.DEFAULTS)
    values.update(overrides)
    return values


def _set_last_prompt(values, days_ago: float) -> None:
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    values[store.KEY_LAST_PROMPT_AT] = moment.replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# progi
# --------------------------------------------------------------------------- #
def test_no_prompt_before_the_threshold(isolated_data):
    values = _values(**{store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES - 1})
    assert support.should_ask(values, config) is False


def test_prompt_once_the_threshold_is_reached(isolated_data):
    values = _values(**{store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES})
    assert support.should_ask(values, config) is True


def test_prompt_does_not_repeat_before_the_cooldown(isolated_data):
    """Po pokazaniu prosby kolejna konwersja nie moze pytac od razu znowu.

    Liczba konwersji jest tu celowo powyzej progu drugiej prosby - inaczej
    test przechodzilby dzieki progowi, a nie dzieki odstepowi czasu, ktory
    ma sprawdzac.
    """
    values = _values(**{
        store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES * 2,
        store.KEY_PROMPT_COUNT: 1,
    })
    _set_last_prompt(values, days_ago=1)
    assert support.should_ask(values, config) is False


def test_prompt_returns_after_the_cooldown(isolated_data):
    values = _values(**{
        store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES * 2,
        store.KEY_PROMPT_COUNT: 1,
    })
    _set_last_prompt(values, days_ago=config.PROMPT_COOLDOWN_DAYS + 1)
    assert support.should_ask(values, config) is True


def test_next_threshold_needs_more_work(isolated_data):
    """Druga prosba dopiero po kolejnych 50 plikach, nie zaraz po pierwszej.

    Pierwsza prosba wypadla przy 50 plikach. Sam uplyw czasu nie wystarcza -
    trzeba jeszcze przekonwertowac kolejne 50.
    """
    values = _values(**{
        store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES,
        store.KEY_PROMPT_COUNT: 1,
    })
    _set_last_prompt(values, days_ago=config.PROMPT_COOLDOWN_DAYS + 1)
    # 50 plikow, prośba juz pokazana -> za malo na druga
    assert support.should_ask(values, config) is False

    # Prog dla drugiej prosby to 2 * PROMPT_AFTER_FILES
    values[store.KEY_CONVERTED_TOTAL] = config.PROMPT_AFTER_FILES * 2 - 1
    assert support.should_ask(values, config) is False

    values[store.KEY_CONVERTED_TOTAL] = config.PROMPT_AFTER_FILES * 2
    assert support.should_ask(values, config) is True


# --------------------------------------------------------------------------- #
# decyzje uzytkownika
# --------------------------------------------------------------------------- #
def test_never_means_never(isolated_data):
    values = _values(**{
        store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES * 10,
        store.KEY_NEVER_PROMPT: True,
    })
    assert support.should_ask(values, config) is False


def test_later_starts_the_cooldown(isolated_data, monkeypatch):
    """Zamkniecie okna ma uspokoic program, a nie wyciszyc go na zawsze."""
    # 100 plikow: po pokazaniu prosby (licznik +1) prog bylby spelniony,
    # wiec jedynym powodem braku kolejnej prosby jest odstep czasu.
    values = _values(**{store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES * 2})
    monkeypatch.setattr(support.dialogs, "ask_choice",
                        lambda *a, **k: support.CHOICE_LATER)

    support.ask_for_support(None, values, config)

    assert values[store.KEY_PROMPT_COUNT] == 1
    assert values[store.KEY_LAST_PROMPT_AT]
    assert values[store.KEY_NEVER_PROMPT] is False
    assert support.should_ask(values, config) is False


def test_support_choice_opens_the_page_and_keeps_asking_allowed(isolated_data, monkeypatch):
    values = _values(**{store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES})
    opened = {"called": False}

    monkeypatch.setattr(support.dialogs, "ask_choice",
                        lambda *a, **k: support.CHOICE_SUPPORT)
    monkeypatch.setattr(support, "open_support_page",
                        lambda cfg: opened.__setitem__("called", True))

    support.ask_for_support(None, values, config)

    assert opened["called"] is True
    assert values[store.KEY_NEVER_PROMPT] is False


def test_donated_stops_the_questions_for_good(isolated_data, monkeypatch):
    values = _values(**{store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES})
    monkeypatch.setattr(support.dialogs, "ask_choice",
                        lambda *a, **k: support.CHOICE_DONATED)
    monkeypatch.setattr(support.dialogs, "show_message", lambda *a, **k: None)

    support.ask_for_support(None, values, config)

    assert values[store.KEY_NEVER_PROMPT] is True
    assert support.should_ask(values, config) is False


def test_never_choice_stops_the_questions(isolated_data, monkeypatch):
    values = _values(**{store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES})
    monkeypatch.setattr(support.dialogs, "ask_choice",
                        lambda *a, **k: support.CHOICE_NEVER)
    monkeypatch.setattr(support.dialogs, "show_message", lambda *a, **k: None)

    support.ask_for_support(None, values, config)

    assert values[store.KEY_NEVER_PROMPT] is True
    assert support.should_ask(values, config) is False


# --------------------------------------------------------------------------- #
# licznik
# --------------------------------------------------------------------------- #
def test_register_conversion_adds_up(isolated_data):
    values = _values()
    support.register_conversion(values, 3)
    support.register_conversion(values, 4)
    assert support.converted_total(values) == 7


def test_register_conversion_ignores_nothing_done(isolated_data):
    values = _values()
    support.register_conversion(values, 0)
    support.register_conversion(values, -5)
    assert support.converted_total(values) == 0


def test_session_counter_increases(isolated_data):
    values = _values()
    support.start_session(values)
    support.start_session(values)
    assert values[store.KEY_SESSIONS] == 2


def test_maybe_ask_returns_false_when_not_due(isolated_data, monkeypatch):
    called = {"ask": False}
    monkeypatch.setattr(support, "ask_for_support",
                        lambda *a, **k: called.__setitem__("ask", True))

    values = _values(**{store.KEY_CONVERTED_TOTAL: 1})
    assert support.maybe_ask(None, values, config) is False
    assert called["ask"] is False


def test_maybe_ask_returns_true_when_due(isolated_data, monkeypatch):
    monkeypatch.setattr(support, "ask_for_support",
                        lambda *a, **k: support.CHOICE_LATER)
    values = _values(**{store.KEY_CONVERTED_TOTAL: config.PROMPT_AFTER_FILES})
    assert support.maybe_ask(None, values, config) is True


def test_prompt_text_uses_correct_polish_plural(isolated_data):
    """'53 plikow' w oknie z prosba o pieniadze wyglada bardzo zle."""
    cases = {
        1: "1 plik.",
        2: "2 pliki.",
        5: "5 plików.",
        22: "22 pliki.",
        25: "25 plików.",
        53: "53 pliki.",
        112: "112 plików.",
    }
    for count, expected in cases.items():
        values = _values(**{store.KEY_CONVERTED_TOTAL: count})
        text = support.prompt_text(values, config)
        assert expected in text, f"dla {count} plikow oczekiwano {expected!r}"


def test_prompt_has_four_ways_out(isolated_data):
    """Uzytkownik musi miec i wsparcie, i sposob na spokojne odmowienie."""
    values = [value for _label, value in support.PROMPT_BUTTONS]
    assert values == [support.CHOICE_SUPPORT, support.CHOICE_DONATED,
                      support.CHOICE_NEVER, support.CHOICE_LATER]


def test_closing_the_prompt_just_snoozes(isolated_data):
    """Escape i X nie moga trwale wyciszac programu."""
    assert support.PROMPT_BUTTONS[-1][1] == support.CHOICE_LATER


def test_open_support_page_without_url_returns_false(isolated_data, monkeypatch):
    """Bez ustawionego adresu nie otwieramy przegladarki i nie udajemy sukcesu."""
    class Cfg:
        SUPPORT_URL = ""

    def boom(*_a, **_k):  # pragma: no cover - nie powinno byc wolane
        raise AssertionError("nie wolno otwierac przegladarki bez adresu")

    monkeypatch.setattr(support.webbrowser, "open", boom)
    assert support.open_support_page(Cfg) is False


def test_open_support_page_with_url_opens_browser(isolated_data, monkeypatch):
    class Cfg:
        SUPPORT_URL = "https://buycoffee.to/ktos"

    opened = {}

    def fake_open(url):
        opened["url"] = url
        return True  # tak samo jak prawdziwe webbrowser.open

    monkeypatch.setattr(support.webbrowser, "open", fake_open)
    assert support.open_support_page(Cfg) is True
    assert opened["url"] == "https://buycoffee.to/ktos"
