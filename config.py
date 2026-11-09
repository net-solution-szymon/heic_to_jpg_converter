"""Configuration for HEIC -> JPG Converter (free, donation-supported build).

This is the only file you have to edit before building a release.
Everything else in the project reads its values from here.

BEFORE YOU SHIP A BUILD
-----------------------
1. Fill in SUPPORT_URL with your buycoffee.to link.
2. Fill in GITHUB_URL if the source is public (it is shown in the licence window).
3. Check SERVER_URL points at your telemetry server.
"""

# --- program identity ------------------------------------------------------
APP_NAME = "HEIC \u2192 JPG Converter"
# Full window title, shown in the title bar and in the taskbar. APP_NAME stays
# the short product name (used in the About window and the diagnostic report).
APP_TITLE = "HEIC --> JPG Converter by Szymon Jankojć"
APP_VERSION = "1.0.1"
# Short name used for the per-user data folder (%APPDATA%/HEIC2JPG on Windows,
# ~/.config/heic2jpg on Linux). Changing it "resets" everyone's counters.
APP_SLUG = "heic2jpg"

# --- telemetry server ------------------------------------------------------
# The API the program reports anonymous statistics to. Leave empty to disable
# telemetry completely - the program will not try to connect at all.
SERVER_URL = ""
TELEMETRY_TIMEOUT = 6.0        # seconds, per request
TELEMETRY_INTERVAL_HOURS = 24  # how often the program reports in

# --- donations -------------------------------------------------------------
# Opened by the "Postaw kawę" button and by the support prompt.
SUPPORT_URL = ""
# Shown as plain text in the About window. Leave empty to hide it.
SUPPORT_EMAIL = ""
# Public repository. Shown in the About window. Leave empty to hide it.
GITHUB_URL = "https://github.com/net-solution-szymon/heic_to_jpg_converter"

# --- when to ask for support ----------------------------------------------
# The prompt appears after this many converted files AND not more often than
# every PROMPT_COOLDOWN_DAYS. Rationale: ask only after the user has clearly
# got value out of the program, and never twice in a row.
PROMPT_AFTER_FILES = 50
PROMPT_COOLDOWN_DAYS = 30

# --- telemetry default -----------------------------------------------------
# The user can always switch this off in Pomoc -> Prywatność. The first-run
# notice explains what is sent, so shipping with it on is honest; shipping
# without telling anyone would not be.
TELEMETRY_ENABLED_BY_DEFAULT = True
