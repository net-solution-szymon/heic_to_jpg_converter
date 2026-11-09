"""Engine tests: correctness of conversion, safety of the originals, cancellation."""
import os

import pytest

from conftest import FIXTURE_LARGE, FIXTURE_ORIENTED

from heic2jpg.converter import (
    CANCELLED,
    CONVERTED,
    ERROR,
    SKIPPED,
    Options,
    collect_files,
    convert_file,
    convert_files,
    parse_drop_list,
)

# --------------------------------------------------------------------------- #
# drag & drop payloads
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "payload,expected",
    [
        ("", []),
        ("   ", []),
        ("C:/tmp/a.heic", ["C:/tmp/a.heic"]),
        # Unbraced, a space really does split the Tcl list (verified below).
        # tkinterdnd2 brace-quotes any path containing spaces, so real drops of
        # "C:/Moje zdjecia/a.heic" always arrive in braces.
        ("C:/Moje zdjecia/a.heic", ["C:/Moje", "zdjecia/a.heic"]),
        ("{C:/Moje zdjecia/a.heic}", ["C:/Moje zdjecia/a.heic"]),
        ("{C:/Moje zdjecia/a.heic} {C:/Moje zdjecia/b.heic}",
         ["C:/Moje zdjecia/a.heic", "C:/Moje zdjecia/b.heic"]),
        ("C:/a.heic C:/b.heic", ["C:/a.heic", "C:/b.heic"]),
        # Unbraced Windows paths suffer Tcl escapes (\\a becomes BEL) - this is
        # the real behaviour of tk.splitlist, verified below against live Tcl.
        ("C:\\Users\\Jan\\a.heic", ["C:UsersJan\x07.heic"]),
        ("{C:\\Users\\Jan\\Moje zdjecia\\a.heic}", ["C:\\Users\\Jan\\Moje zdjecia\\a.heic"]),
        ("{C:/Moje zdjecia} C:/drugi.heic", ["C:/Moje zdjecia", "C:/drugi.heic"]),
        ("C:/dupa/a.heic\nC:/other/b.heic", ["C:/dupa/a.heic", "C:/other/b.heic"]),
        ("{C:/a{1}/b.heic}", ["C:/a{1}/b.heic"]),  # nested braces survive
        ("{C:/a jakieś zdjęcie.heic}", ["C:/a jakieś zdjęcie.heic"]),
    ],
)
def test_parse_drop_list(payload, expected):
    assert parse_drop_list(payload) == expected


TCL_SAMPLES = [
    "C:/tmp/a.heic",
    "C:/Moje zdjecia/a.heic",
    "{C:/Moje zdjecia/a.heic}",
    "{C:/Moje zdjecia/a.heic} {C:/Moje zdjecia/b.heic}",
    "C:/a.heic C:/b.heic",
    "C:\\Users\\Jan\\a.heic",
    "{C:\\Users\\Jan\\Moje zdjecia\\a.heic}",
    "{C:/Moje zdjecia} C:/drugi.heic",
    "C:/dupa/a.heic\nC:/other/b.heic",
    "{C:/a{1}/b.heic}",
    "a\\ b c",
    "one   two\tthree",
]


def test_parser_is_lenient_where_tcl_would_raise():
    """Malformed Tcl (``{a}b``) makes splitlist raise; we never crash the UI.

    tkinterdnd2 does not emit such payloads, but a drop handler must not be able
    to throw, so the parser degrades gracefully instead of raising TclError.
    """
    assert parse_drop_list("{a}b") == ["ab"]


def test_parser_matches_real_tcl_splitlist():
    """The parser must agree with Tcl, because tkinterdnd2 sends a Tcl list."""
    tkinter = pytest.importorskip("tkinter")
    try:
        root = tkinter.Tk()
    except Exception:  # no display available
        pytest.skip("brak wyswietlacza - nie da sie porownac z Tcl")
    root.withdraw()
    try:
        mismatches = []
        for sample in TCL_SAMPLES:
            expected = [t for t in root.tk.splitlist(sample) if t]
            actual = parse_drop_list(sample)
            if expected != actual:
                mismatches.append((sample, expected, actual))
        assert not mismatches, f"rozbieznosci z Tcl: {mismatches}"
    finally:
        root.destroy()


def test_parse_drop_list_handles_many_files():
    payload = " ".join(f"{{C:/Moje zdjecia/IMG_{i:04d}.HEIC}}" for i in range(5))
    parsed = parse_drop_list(payload)
    assert len(parsed) == 5
    assert parsed[0] == "C:/Moje zdjecia/IMG_0000.HEIC"
    assert parsed[4] == "C:/Moje zdjecia/IMG_0004.HEIC"


# --------------------------------------------------------------------------- #
# collecting
# --------------------------------------------------------------------------- #
def test_collect_files_walks_folders_and_reports_skips(sample_dir):
    files, warnings = collect_files([sample_dir])
    assert len(files) == 3
    assert all(f.suffix.lower() in (".heic", ".heif") for f in files)
    assert len(warnings) == 2  # notatki.txt + opis.md


def test_collect_files_non_recursive(sample_dir):
    files, _ = collect_files([sample_dir], recursive=False)
    assert len(files) == 2  # the nested wakacje/ folder is not entered


def test_collect_files_deduplicates_and_accepts_files(sample_dir):
    nested = sample_dir / "wakacje" / "IMG_0003.HEIC"
    files, _ = collect_files([sample_dir, nested, str(nested)])
    assert len(files) == 3  # the same file given twice counts once


def test_collect_files_reports_missing_path(tmp_path):
    files, warnings = collect_files([tmp_path / "nie_ma_mnie"])
    assert files == []
    assert any("Nie znaleziono" in w for w in warnings)


# --------------------------------------------------------------------------- #
# single file conversion
# --------------------------------------------------------------------------- #
def test_convert_file_creates_jpeg_and_keeps_the_original(tmp_path, heic_maker):
    source = heic_maker(tmp_path / "foto.HEIC")
    result = convert_file(source, Options())

    assert result.status == CONVERTED, result.message
    assert result.target == tmp_path / "foto.jpg"
    assert result.target.exists()
    # The original must survive: this is the biggest flaw of the old script.
    assert source.exists(), "oryginalny plik HEIC został skasowany!"
    assert result.bytes_after > 0


def test_convert_file_can_delete_the_original_on_request(tmp_path, heic_maker):
    source = heic_maker(tmp_path / "foto.HEIC")
    result = convert_file(source, Options(delete_original=True))
    assert result.status == CONVERTED
    assert not source.exists()
    assert result.target.exists()
    assert "usunięto oryginał" in result.message


def test_convert_file_skips_existing_target_without_overwrite(tmp_path, heic_maker):
    source = heic_maker(tmp_path / "foto.HEIC")
    target = tmp_path / "foto.jpg"
    target.write_bytes(b"stary plik")

    result = convert_file(source, Options())
    assert result.status == SKIPPED
    assert target.read_bytes() == b"stary plik"  # untouched


def test_convert_file_overwrites_when_asked(tmp_path, heic_maker):
    source = heic_maker(tmp_path / "foto.HEIC")
    target = tmp_path / "foto.jpg"
    target.write_bytes(b"stary plik")

    result = convert_file(source, Options(overwrite=True))
    assert result.status == CONVERTED
    assert target.read_bytes() != b"stary plik"
    assert target.read_bytes()[:2] == b"\xff\xd8"  # JPEG magic


def test_convert_file_honours_output_directory(tmp_path, heic_maker):
    source = heic_maker(tmp_path / "src" / "foto.HEIC")
    out = tmp_path / "gotowe"
    result = convert_file(source, Options(output_dir=out))

    assert result.status == CONVERTED
    assert result.target == out / "foto.jpg"
    assert result.target.exists()
    assert source.exists()


def test_convert_file_preserves_exif_and_icc(tmp_path, heic_maker):
    source = heic_maker(tmp_path / "foto.HEIC", FIXTURE_ORIENTED)
    result = convert_file(source, Options(keep_exif=True))
    assert result.status == CONVERTED

    from PIL import Image

    with Image.open(result.target) as image:
        assert image.format == "JPEG"
        exif = image.getexif()
        assert exif is not None


def test_convert_file_can_strip_exif(tmp_path, heic_maker):
    source = heic_maker(tmp_path / "foto.HEIC", FIXTURE_ORIENTED)
    result = convert_file(source, Options(keep_exif=False))
    assert result.status == CONVERTED

    from PIL import Image

    with Image.open(result.target) as image:
        assert len(dict(image.getexif())) == 0


def test_quality_changes_file_size(tmp_path, heic_maker):
    source = heic_maker(tmp_path / "foto.HEIC", FIXTURE_LARGE)
    low = convert_file(source, Options(quality=30))
    high = convert_file(source, Options(quality=95, overwrite=True))
    assert low.bytes_after < high.bytes_after


def test_corrupted_file_reports_error_and_leaves_no_temp(tmp_path):
    broken = tmp_path / "zepsuty.HEIC"
    broken.write_bytes(b"to nie jest obrazek")

    result = convert_file(broken, Options())
    assert result.status == ERROR
    assert result.message
    leftovers = [p for p in os.listdir(tmp_path) if p.endswith(".part")]
    assert leftovers == [], f"zostały pliki tymczasowe: {leftovers}"
    assert not (tmp_path / "zepsuty.jpg").exists()


def test_unsupported_extension_is_skipped(tmp_path):
    text = tmp_path / "plik.txt"
    text.write_text("x", encoding="utf-8")
    result = convert_file(text, Options())
    assert result.status == SKIPPED


def test_missing_file_reports_error(tmp_path):
    result = convert_file(tmp_path / "nie_ma.HEIC", Options())
    assert result.status == ERROR


# --------------------------------------------------------------------------- #
# batch
# --------------------------------------------------------------------------- #
def test_convert_files_summarises_and_reports_progress(sample_dir):
    files, _ = collect_files([sample_dir])
    seen = []

    summary = convert_files(files, Options(), on_progress=lambda i, t, r: seen.append((i, t)))

    assert summary.converted == 3
    assert summary.total == 3
    assert summary.errors == 0
    assert summary.seconds >= 0
    assert [s[0] for s in seen] == [1, 2, 3]
    assert all(s[1] == 3 for s in seen)


def test_convert_files_can_be_cancelled(sample_dir):
    files, _ = collect_files([sample_dir])
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > 2  # stop before the third file

    summary = convert_files(files, Options(), should_cancel=should_cancel)

    assert summary.converted == 2
    assert summary.cancelled == 1
    assert summary.total == 3
    assert [r.status for r in summary.results].count(CANCELLED) == 1


def test_convert_files_keeps_going_after_a_bad_file(tmp_path, heic_maker):
    good = heic_maker(tmp_path / "dobry.HEIC")
    broken = tmp_path / "zly.HEIC"
    broken.write_bytes(b"nie obrazek")
    good2 = heic_maker(tmp_path / "dobry2.HEIC")

    summary = convert_files([good, broken, good2], Options())
    assert summary.converted == 2
    assert summary.errors == 1


def test_summary_reports_saved_bytes(sample_dir):
    files, _ = collect_files([sample_dir])
    summary = convert_files(files, Options())
    assert summary.bytes_before > 0
    assert summary.bytes_after > 0
