"""The one place that keeps small pieces of state between runs.

Everything the program remembers about a user lives in a single JSON file in
the user's data directory:

    Windows:  %APPDATA%/HEIC2JPG/data.json
    Linux:    ~/.config/heic2jpg/data.json
    macOS:    ~/Library/Application Support/heic2jpg/data.json

That includes the installation identifier (telemetry), the conversion
counters (support prompts) and the user's preference switches. One file, easy
to inspect and easy to delete - "uninstalling" the program's memory is
removing this file and nothing else.

Writes are atomic (write to a temp file, then replace) so a crash in the
middle cannot leave a half-written, unreadable file behind.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Keys, in one place, so typos fail at import rather than at runtime.
KEY_INSTALL_ID = "install_id"
KEY_FIRST_SEEN = "first_seen"
KEY_LAST_PING = "last_ping"
KEY_CONVERTED_TOTAL = "converted_total"
KEY_SESSIONS = "sessions"
KEY_LAST_PROMPT_AT = "last_prompt_at"
KEY_PROMPT_COUNT = "prompt_count"
KEY_NEVER_PROMPT = "never_prompt"
KEY_TELEMETRY = "telemetry_enabled"

DEFAULTS = {
    KEY_INSTALL_ID: "",
    KEY_FIRST_SEEN: "",
    KEY_LAST_PING: "",
    KEY_CONVERTED_TOTAL: 0,
    KEY_SESSIONS: 0,
    KEY_LAST_PROMPT_AT: "",
    KEY_PROMPT_COUNT: 0,
    KEY_NEVER_PROMPT: False,
    KEY_TELEMETRY: True,
}


def data_dir() -> Path:
    """Per-user directory for program data. Created on first use."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        target = base / "HEIC2JPG"
    elif sys.platform == "darwin":
        target = Path.home() / "Library" / "Application Support" / "heic2jpg"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        target = base / "heic2jpg"

    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        # A locked-down machine must not stop the program from working; fall
        # back to the home directory, and if even that fails, to the temp dir.
        for fallback in (Path.home() / ".heic2jpg", Path(tempfile.gettempdir())):
            try:
                fallback.mkdir(parents=True, exist_ok=True)
                return fallback
            except OSError:
                continue
    return target


def data_file() -> Path:
    return data_dir() / "data.json"


def load() -> dict:
    """Read the stored values, filling in anything missing with defaults.

    A corrupt or unreadable file is treated as empty rather than fatal: losing
    a counter must never stop somebody from converting their photos.
    """
    values = dict(DEFAULTS)
    try:
        raw = json.loads(data_file().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for key, default in DEFAULTS.items():
                stored = raw.get(key, default)
                # Guard against a hand-edited file with the wrong type.
                values[key] = stored if isinstance(stored, type(default)) else default
    except (OSError, ValueError):
        pass
    return values


def save(values: dict) -> bool:
    """Write the values out atomically. Returns False if nothing was written."""
    target = data_file()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handle, temp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(values, stream, ensure_ascii=False, indent=2)
        os.replace(temp_name, target)
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# convenience accessors
# --------------------------------------------------------------------------- #
def bump(values: dict, key: str, amount: int = 1) -> dict:
    """Increase an integer counter and save. Returns the updated values."""
    values[key] = int(values.get(key, 0)) + amount
    save(values)
    return values


def set_value(values: dict, key: str, value) -> dict:
    values[key] = value
    save(values)
    return values
