"""HEIC/HEIF -> JPEG conversion engine.

Deliberately free of Tkinter so it can be unit tested and reused in a CLI.

Design rules
------------
* **Never touch the source file** unless the caller explicitly asks for it
  (``delete_original=True``). A converter that eats originals is a converter
  nobody trusts with their photos.
* **Atomic writes**: the JPEG is written to a temporary name and then renamed,
  so an interrupted run never leaves a half-written picture.
* **Big-endian safe overwrite decisions**: an existing target is skipped by
  default and only replaced when ``overwrite=True``.
* **EXIF and ICC profile survive** the conversion, and the orientation tag is
  applied to the pixels (phone photos come out upright, not rotated).
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_INPUT = {".heic", ".heif"}
SUPPORTED_OUTPUT = {".jpg", ".jpeg"}

# Statuses reported per file (translated in the UI layer).
CONVERTED = "converted"
SKIPPED = "skipped"
ERROR = "error"
CANCELLED = "cancelled"

_heif_registered = False


def register_heif() -> bool:
    """Register the HEIF opener exactly once. Returns False if unavailable.

    Deliberately ``pi-heif`` and NOT ``pillow-heif``.

    Both packages come from the same author and expose the same
    ``register_heif_opener()``, but their binary wheels are licensed
    differently, and that difference decides whether this product can be sold
    as closed source:

        pillow-heif wheels:  GPLv2  - they bundle libx265 (GPL-2.0) for encoding
        pi-heif wheels:      LGPLv3 - decode only, no x265 at all

    This application only *decodes* HEIC, so the encoder - and with it the GPL
    component - is dead weight. Do not "simplify" this import back to
    pillow-heif: that would silently pull a GPLv2 library back into a
    commercial closed-source build. See legal/AUDYT-praw-autorskich.md.
    """
    global _heif_registered
    if _heif_registered:
        return True
    try:
        from pi_heif import register_heif_opener

        register_heif_opener()
        _heif_registered = True
        return True
    except Exception:  # pragma: no cover - missing optional dependency
        return False


# --------------------------------------------------------------------------- #
# options and results
# --------------------------------------------------------------------------- #
@dataclass
class Options:
    quality: int = 90
    keep_exif: bool = True
    overwrite: bool = False
    delete_original: bool = False
    recursive: bool = True
    output_dir: Path | None = None  # None -> write next to the source file

    def target_for(self, source: Path) -> Path:
        name = source.with_suffix(".jpg").name
        if self.output_dir is None:
            return source.with_suffix(".jpg")
        return Path(self.output_dir) / name


@dataclass
class FileResult:
    source: Path
    target: Path | None = None
    status: str = ERROR
    message: str = ""
    bytes_before: int = 0
    bytes_after: int = 0

    @property
    def saved_bytes(self) -> int:
        return max(0, self.bytes_before - self.bytes_after)


@dataclass
class Summary:
    converted: int = 0
    skipped: int = 0
    errors: int = 0
    cancelled: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    seconds: float = 0.0
    results: list[FileResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.converted + self.skipped + self.errors + self.cancelled

    @property
    def saved_bytes(self) -> int:
        return max(0, self.bytes_before - self.bytes_after)

    @property
    def speed(self) -> float:
        return self.converted / self.seconds if self.seconds > 0 else 0.0


# --------------------------------------------------------------------------- #
# drag & drop payload parsing
# --------------------------------------------------------------------------- #
_TCL_ESCAPES = {
    "a": "\x07", "b": "\x08", "f": "\x0c", "n": "\n",
    "r": "\r", "t": "\t", "v": "\x0b",
}


def _tcl_escape(text: str, index: int) -> tuple[str, int]:
    """Decode the backslash escape starting at ``text[index]`` ('\\\\').

    Mirrors Tcl: known escapes are translated, an unknown escape simply loses
    its backslash, and a trailing backslash stays literal.
    """
    following = text[index + 1] if index + 1 < len(text) else ""
    if not following:
        return "\\", index + 1
    if following == "\\":
        return "\\", index + 2
    if following in _TCL_ESCAPES:
        return _TCL_ESCAPES[following], index + 2
    if following == "\n":
        return " ", index + 2  # line continuation
    if following in "xu":
        width = 2 if following == "x" else 4
        digits = text[index + 2:index + 2 + width]
        # Tcl stops at the first non-hex character.
        taken = ""
        for char in digits:
            if char.lower() in "0123456789abcdef":
                taken += char
            else:
                break
        if taken:
            try:
                return chr(int(taken, 16)), index + 2 + len(taken)
            except ValueError:  # pragma: no cover
                pass
    if following in "01234567":
        digits = text[index + 1:index + 4]
        taken = ""
        for char in digits:
            if char in "01234567":
                taken += char
            else:
                break
        if taken:
            return chr(int(taken, 8)), index + 1 + len(taken)
    return following, index + 2


def parse_drop_list(data: str) -> list[str]:
    """Parse a tkinterdnd2 drop payload into a list of paths.

    tkinterdnd2 hands over a **Tcl list**: plain words when a path has no
    spaces, brace-quoted when it does::

        {C:/Moje zdjecia/a.heic} {C:/Moje zdjecia/b.heic}
        C:/tmp/a.heic C:/tmp/b.heic

    The original code used ``data.strip("{}")``, which mangles a drop of more
    than one file. This implementation follows real Tcl semantics (verified
    against ``tk.splitlist`` in the test suite): inside braces everything is
    literal, outside them Tcl escapes apply.
    """
    if not data:
        return []

    tokens: list[str] = []
    current: list[str] = []
    started = False
    depth = 0
    index = 0
    length = len(data)

    while index < length:
        char = data[index]

        if depth > 0:  # inside braces: literal content, nested braces allowed
            if char == "{":
                depth += 1
                current.append(char)
            elif char == "}":
                depth -= 1
                if depth > 0:
                    current.append(char)
            else:
                current.append(char)
            started = True
            index += 1
            continue

        if char in " \t\r\n":  # token separator
            if started:
                tokens.append("".join(current))
                current, started = [], False
            index += 1
            continue

        if char == "{":
            depth = 1
            started = True
            index += 1
            continue

        if char == "\\":
            decoded, index = _tcl_escape(data, index)
            current.append(decoded)
            started = True
            continue

        current.append(char)
        started = True
        index += 1

    if started:
        tokens.append("".join(current))

    return [token for token in tokens if token]


# --------------------------------------------------------------------------- #
# collecting inputs
# --------------------------------------------------------------------------- #
def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_INPUT


def collect_files(paths, recursive: bool = True) -> tuple[list[Path], list[str]]:
    """Expand files and folders into a de-duplicated, sorted list of HEIC files.

    Returns ``(files, warnings)`` so the UI can tell the user what it ignored.
    """
    found: dict[str, Path] = {}
    warnings: list[str] = []

    for raw in paths:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if path.is_dir():
            pattern = "**/*" if recursive else "*"
            for candidate in sorted(path.glob(pattern)):
                if candidate.is_file():
                    if is_supported(candidate):
                        found.setdefault(str(candidate.resolve()), candidate)
                    else:
                        warnings.append(f"Pomijam (nieobsługiwany): {candidate.name}")
        elif path.is_file():
            if is_supported(path):
                found.setdefault(str(path.resolve()), path)
            else:
                warnings.append(f"Pomijam (nieobsługiwany): {path.name}")
        else:
            warnings.append(f"Nie znaleziono ścieżki: {path}")

    return sorted(found.values(), key=lambda p: str(p).lower()), warnings


# --------------------------------------------------------------------------- #
# converting
# --------------------------------------------------------------------------- #
def _safe_stem(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return cleaned or "image"


def convert_file(source: Path, options: Options) -> FileResult:
    """Convert a single file. Never raises: failures come back as FileResult."""
    source = Path(source)
    result = FileResult(source=source)

    if not register_heif():
        result.status = ERROR
        result.message = (
            "Brak biblioteki do obslugi HEIC (pakiet 'pi-heif'). "
            "Zainstaluj: pip install pi-heif"
        )
        return result

    if not source.is_file():
        result.status = ERROR
        result.message = "Plik nie istnieje."
        return result

    if not is_supported(source):
        result.status = SKIPPED
        result.message = "Nieobsługiwany format."
        return result

    target = options.target_for(source)
    result.target = target

    try:
        result.bytes_before = source.stat().st_size
    except OSError:
        result.bytes_before = 0

    if target.exists() and not options.overwrite:
        result.status = SKIPPED
        result.message = "Plik wynikowy już istnieje."
        try:
            result.bytes_after = target.stat().st_size
        except OSError:
            pass
        return result

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        result.status = ERROR
        result.message = f"Nie mogę utworzyć katalogu docelowego: {exc}"
        return result

    from PIL import Image, ImageOps

    temp = target.with_name(f".{_safe_stem(target.stem)}{target.suffix}.part")
    try:
        with Image.open(source) as image:
            frames = getattr(image, "n_frames", 1)
            # exif_transpose both applies the orientation and drops the tag,
            # so photos shot in portrait are not saved sideways.
            oriented = ImageOps.exif_transpose(image)
            exif = oriented.getexif() if options.keep_exif else None
            icc = oriented.info.get("icc_profile")

            save_kwargs = {
                "format": "JPEG",
                "quality": max(1, min(int(options.quality), 100)),
                "optimize": True,
                "progressive": True,
                "subsampling": 0 if options.quality >= 90 else 2,
            }
            if exif:
                save_kwargs["exif"] = exif.tobytes()
            if icc:
                save_kwargs["icc_profile"] = icc

            if oriented.mode not in ("RGB", "L"):
                oriented = oriented.convert("RGB")

            oriented.save(temp, **save_kwargs)

        os.replace(temp, target)
        result.status = CONVERTED
        result.bytes_after = target.stat().st_size
        notes = []
        if frames > 1:
            notes.append(f"skonwertowano pierwszą z {frames} klatek")
        if options.delete_original:
            source.unlink(missing_ok=True)
            notes.append("usunięto oryginał")
        result.message = "; ".join(notes)
        return result

    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the batch
        result.status = ERROR
        result.message = f"{type(exc).__name__}: {exc}"
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return result


def convert_files(files, options: Options, on_progress=None, should_cancel=None) -> Summary:
    """Convert a batch.

    ``on_progress(index, total, result)`` is called after each file;
    ``should_cancel()`` is polled before each file so the UI can stop the run.
    """
    files = [Path(f) for f in files]
    summary = Summary()
    started = time.monotonic()
    total = len(files)

    for index, source in enumerate(files, start=1):
        if should_cancel is not None and should_cancel():
            remaining = files[index - 1:]
            for pending in remaining:
                result = FileResult(source=pending, status=CANCELLED, message="Anulowano.")
                summary.results.append(result)
                summary.cancelled += 1
            if on_progress:
                on_progress(total, total, summary.results[-1])
            break

        result = convert_file(source, options)
        summary.results.append(result)
        summary.bytes_before += result.bytes_before
        summary.bytes_after += result.bytes_after

        if result.status == CONVERTED:
            summary.converted += 1
        elif result.status == SKIPPED:
            summary.skipped += 1
        elif result.status == CANCELLED:
            summary.cancelled += 1
        else:
            summary.errors += 1

        if on_progress:
            on_progress(index, total, result)

    summary.seconds = time.monotonic() - started
    return summary
