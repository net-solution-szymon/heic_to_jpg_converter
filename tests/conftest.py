"""Wspolne fixtures.

Pliki HEIC uzywane w testach leza gotowe w ``tests/fixtures/`` i sa kopiowane
w miejsce wskazane przez test.

DLACZEGO nie generujemy ich w testach: program korzysta z pakietu ``pi-heif``,
ktory (celowo) nie zawiera enkodera HEVC - wlasnie dzieki temu w wydaniu nie ma
biblioteki GPLv2 (``libx265``). Bez enkodera testy nie moga jednak zapisac
pliku HEIC, wiec korzystaja z gotowych plikow. Odswiezenie ich opisuje
``tools_make_test_fixtures.py``.
"""
import pathlib
import shutil
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURES = ROOT / "tests" / "fixtures"

FIXTURE_SMALL = "photo_small.heic"        # podstawowy obraz 640x480
FIXTURE_SECOND = "photo_second.heic"      # inny obraz 800x600
FIXTURE_LARGE = "photo_large.heic"        # 1200x900, do testu jakosci
FIXTURE_ORIENTED = "photo_oriented.heic"  # z tagiem orientacji EXIF


def fixture_path(name: str) -> pathlib.Path:
    path = FIXTURES / name
    if not path.is_file():
        raise AssertionError(
            f"Brak pliku testowego: {path}\n"
            "Uruchom tools_make_test_fixtures.py w srodowisku deweloperskim "
            "z zainstalowanym pillow-heif."
        )
    return path


def copy_fixture(destination: pathlib.Path, name: str = FIXTURE_SMALL) -> pathlib.Path:
    destination = pathlib.Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture_path(name), destination)
    return destination


@pytest.fixture
def heic_maker():
    """Zwraca funkcje kopiujaca gotowy plik HEIC pod wskazana sciezke.

    Uzycie:
        heic_maker(tmp_path / "foto.HEIC")                       # podstawowy
        heic_maker(tmp_path / "foto.HEIC", FIXTURE_ORIENTED)     # z EXIF
        heic_maker(tmp_path / "duzy.HEIC", FIXTURE_LARGE)        # duzy
    """

    def _copy(destination, name: str = FIXTURE_SMALL) -> pathlib.Path:
        return copy_fixture(destination, name)

    return _copy


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Przekierowuje dane programu do katalogu tymczasowego.

    Bez tego testy pisalyby do prawdziwego katalogu uzytkownika (liczniki,
    identyfikator instalacji) i wzajemnie sie nadpisywaly.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return tmp_path


@pytest.fixture
def sample_dir(tmp_path):
    """Katalog z trzema zdjeciami HEIC, podfolderem i plikiem nie-obrazem."""
    root = tmp_path / "zdjecia"
    copy_fixture(root / "IMG_0001.HEIC", FIXTURE_SMALL)
    copy_fixture(root / "IMG_0002.heic", FIXTURE_SECOND)
    copy_fixture(root / "wakacje" / "IMG_0003.HEIC", FIXTURE_SMALL)
    (root / "notatki.txt").write_text("to nie jest zdjecie", encoding="utf-8")
    (root / "wakacje" / "opis.md").write_text("# nie zdjecie", encoding="utf-8")
    return root
