"""Testy pamieci programu (store.py).

To najwazniejszy plik do przetestowania: jesli zapis stanu sie zepsuje,
uzytkownik traci liczniki, a program zaczyna pytac o wsparcie od nowa.
"""
import json

from heic2jpg import store


def test_defaults_when_nothing_stored(isolated_data):
    values = store.load()
    assert values[store.KEY_CONVERTED_TOTAL] == 0
    assert values[store.KEY_SESSIONS] == 0
    assert values[store.KEY_NEVER_PROMPT] is False
    assert values[store.KEY_TELEMETRY] is True
    assert values[store.KEY_INSTALL_ID] == ""


def test_save_and_load_roundtrip(isolated_data):
    values = store.load()
    values[store.KEY_CONVERTED_TOTAL] = 42
    values[store.KEY_INSTALL_ID] = "abc-123"
    assert store.save(values)

    again = store.load()
    assert again[store.KEY_CONVERTED_TOTAL] == 42
    assert again[store.KEY_INSTALL_ID] == "abc-123"


def test_data_file_lives_in_the_user_directory(isolated_data):
    path = store.data_file()
    assert path.parent.exists()
    assert str(isolated_data) in str(path)


def test_corrupt_file_is_ignored_not_fatal(isolated_data):
    """Uszkodzony plik nie moze uniemozliwic korzystania z programu."""
    store.data_file().parent.mkdir(parents=True, exist_ok=True)
    store.data_file().write_text("{to nie jest json", encoding="utf-8")

    values = store.load()
    assert values[store.KEY_CONVERTED_TOTAL] == 0


def test_wrong_type_in_file_falls_back_to_default(isolated_data):
    """Recznie poprawiony plik z tekstem zamiast liczby nie moze wysypac programu."""
    store.data_file().parent.mkdir(parents=True, exist_ok=True)
    store.data_file().write_text(
        json.dumps({store.KEY_CONVERTED_TOTAL: "duzo"}), encoding="utf-8")

    values = store.load()
    assert values[store.KEY_CONVERTED_TOTAL] == 0


def test_unknown_keys_are_dropped(isolated_data):
    store.data_file().parent.mkdir(parents=True, exist_ok=True)
    store.data_file().write_text(
        json.dumps({"cos_dodatkowego": 1, store.KEY_SESSIONS: 3}), encoding="utf-8")

    values = store.load()
    assert values[store.KEY_SESSIONS] == 3
    assert "cos_dodatkowego" not in values


def test_bump_increases_and_saves(isolated_data):
    values = store.load()
    store.bump(values, store.KEY_SESSIONS)
    store.bump(values, store.KEY_SESSIONS)
    store.bump(values, store.KEY_CONVERTED_TOTAL, 7)

    again = store.load()
    assert again[store.KEY_SESSIONS] == 2
    assert again[store.KEY_CONVERTED_TOTAL] == 7


def test_saving_leaves_no_temporary_files(isolated_data):
    """Zapis jest atomowy - po udanym zapisie nie zostaje plik .tmp."""
    values = store.load()
    store.save(values)

    leftovers = list(store.data_dir().glob("*.tmp"))
    assert leftovers == []
