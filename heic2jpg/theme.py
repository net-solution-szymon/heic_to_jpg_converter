"""Colour palette, fonts and small styling helpers.

One place to change the look. The palette is a dark "editor" style: deep navy
surfaces, a single vivid accent, semantic colours for success/warning/danger.
"""
from __future__ import annotations

import sys

import customtkinter as ctk

# --------------------------------------------------------------------------- #
# palette
# --------------------------------------------------------------------------- #
class Palette:
    bg = "#0f131b"          # window background
    surface = "#171d29"     # cards
    surface_alt = "#1f2735"  # inputs, drop zone
    surface_high = "#28313f"  # hover
    border = "#2c3646"

    text = "#e8edf5"
    text_muted = "#93a1b5"
    text_faint = "#5d6b80"

    accent = "#4f8cff"
    accent_hover = "#6ba0ff"
    accent_press = "#3d76e0"
    accent_soft = "#1b2b46"   # tinted background for accent areas

    success = "#35c48a"
    success_soft = "#13342a"
    warning = "#f0b34a"
    warning_soft = "#3a2d16"
    danger = "#ff5f5f"
    danger_soft = "#3a1c1c"


def font_family() -> str:
    """Prefer the native UI font, fall back to something universally present."""
    if sys.platform.startswith("win"):
        return "Segoe UI"
    if sys.platform == "darwin":
        return "SF Pro Text"
    return "DejaVu Sans"


FAMILY = None  # filled in by init_fonts()


def init_fonts() -> None:
    global FAMILY
    FAMILY = font_family()


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FAMILY or font_family(), size=size, weight=weight)


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
PAD = 18
RADIUS = 12
RADIUS_SMALL = 8


def apply_appearance() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    init_fonts()


# --------------------------------------------------------------------------- #
# reusable widgets
# --------------------------------------------------------------------------- #
def card(master, **kwargs) -> ctk.CTkFrame:
    """A rounded 'card' surface used throughout the layout."""
    options = dict(fg_color=Palette.surface, corner_radius=RADIUS, border_width=1,
                   border_color=Palette.border)
    options.update(kwargs)
    return ctk.CTkFrame(master, **options)


def primary_button(master, text: str, command, **kwargs) -> ctk.CTkButton:
    options = dict(
        text=text,
        command=command,
        fg_color=Palette.accent,
        hover_color=Palette.accent_hover,
        text_color="#ffffff",
        corner_radius=RADIUS_SMALL,
        height=38,
        font=font(13, "bold"),
    )
    options.update(kwargs)
    return ctk.CTkButton(master, **options)


def ghost_button(master, text: str, command, **kwargs) -> ctk.CTkButton:
    options = dict(
        text=text,
        command=command,
        fg_color=Palette.surface_alt,
        hover_color=Palette.surface_high,
        text_color=Palette.text,
        border_width=1,
        border_color=Palette.border,
        corner_radius=RADIUS_SMALL,
        height=38,
        font=font(13),
    )
    options.update(kwargs)
    return ctk.CTkButton(master, **options)


def section_title(master, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=text.upper(),
        font=font(11, "bold"),
        text_color=Palette.text_faint,
        anchor="w",
    )


def muted(master, text: str, **kwargs) -> ctk.CTkLabel:
    options = dict(text=text, font=font(12), text_color=Palette.text_muted, anchor="w")
    options.update(kwargs)
    return ctk.CTkLabel(master, **options)


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(size)} B"
            # Polish uses a decimal comma.
            return f"{size:.1f}".replace(".", ",") + f" {unit}"
        size /= 1024
    return f"{size:.1f}".replace(".", ",") + " GB"


def plural(count: int, one: str, few: str, many: str) -> str:
    """Polish plural forms: 1 plik, 2-4 pliki, 5+ plików, 22 pliki, 25 plików."""
    if count == 1:
        return one
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return few
    return many


def files_label(count: int) -> str:
    return f"{count} {plural(count, 'plik', 'pliki', 'plików')}"


# --------------------------------------------------------------------------- #
# icons
# --------------------------------------------------------------------------- #
# Unicode symbols are a trap: characters like ⤓, ⋮ or ✕ are missing from many
# common fonts and render as empty boxes. Every icon is therefore drawn with
# Pillow, which is already a dependency - it looks identical everywhere.
# Only the *Pillow* image is cached, never the CTkImage.
#
# A CTkImage wraps a Tk photo image bound to one Tcl interpreter. Caching those
# and reusing them after the window is recreated raises
# "TclError: image pyimageN does not exist" - and because such an error fires
# inside an `after` callback it can silently kill the event chain. Keying the
# cache by the root's id() is not enough either: Python reuses ids after the old
# window is garbage collected, so a stale entry looks valid again.
_PIL_CACHE: dict = {}


def icon(name: str, size: int = 16, color: str | None = None) -> "ctk.CTkImage":
    from PIL import Image, ImageDraw

    colour = color or Palette.text_muted
    key = (name, size, colour)
    cached = _PIL_CACHE.get(key)
    if cached is not None:
        return ctk.CTkImage(light_image=cached, dark_image=cached, size=(size, size))

    scale = 4  # supersample, then downscale: smooth edges without antialias code
    side = size * scale
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    width = max(scale, side // 9)

    if name == "drop":
        # an arrow pointing down into a tray
        draw.line([(side // 2, side * 0.10), (side // 2, side * 0.62)],
                  fill=colour, width=width)
        draw.line([(side * 0.28, side * 0.44), (side // 2, side * 0.66),
                   (side * 0.72, side * 0.44)], fill=colour, width=width,
                  joint="curve")
        draw.line([(side * 0.14, side * 0.86), (side * 0.86, side * 0.86)],
                  fill=colour, width=width)
    elif name == "close":
        pad = side * 0.26
        draw.line([(pad, pad), (side - pad, side - pad)], fill=colour, width=width)
        draw.line([(side - pad, pad), (pad, side - pad)], fill=colour, width=width)
    elif name == "menu":
        radius = side * 0.09
        for factor in (0.24, 0.5, 0.76):
            cx, cy = side / 2, side * factor
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                         fill=colour)
    elif name == "check":
        draw.line([(side * 0.20, side * 0.54), (side * 0.42, side * 0.74),
                   (side * 0.80, side * 0.28)], fill=colour, width=width,
                  joint="curve")
    elif name == "photo":
        draw.ellipse((side * 0.14, side * 0.14, side * 0.38, side * 0.38), fill=colour)
        draw.polygon([(side * 0.10, side * 0.84), (side * 0.40, side * 0.42),
                      (side * 0.64, side * 0.84)], fill=colour)
        draw.polygon([(side * 0.46, side * 0.84), (side * 0.68, side * 0.56),
                      (side * 0.90, side * 0.84)], fill=colour)
    elif name == "folder":
        draw.rounded_rectangle((side * 0.10, side * 0.24, side * 0.90, side * 0.80),
                               radius=side * 0.08, outline=colour, width=width)
        draw.line([(side * 0.10, side * 0.38), (side * 0.42, side * 0.38)],
                  fill=colour, width=width)
    elif name == "warn":
        draw.polygon([(side / 2, side * 0.12), (side * 0.92, side * 0.84),
                      (side * 0.08, side * 0.84)], outline=colour, width=width)
        draw.line([(side / 2, side * 0.36), (side / 2, side * 0.60)],
                  fill=colour, width=width)
        draw.ellipse((side / 2 - width, side * 0.68, side / 2 + width, side * 0.72),
                     fill=colour)
    elif name == "info":
        draw.ellipse((side * 0.08, side * 0.08, side * 0.92, side * 0.92),
                     outline=colour, width=width)
        draw.ellipse((side * 0.44, side * 0.26, side * 0.56, side * 0.38), fill=colour)
        draw.line([(side / 2, side * 0.46), (side / 2, side * 0.74)],
                  fill=colour, width=width)
    elif name == "question":
        draw.ellipse((side * 0.08, side * 0.08, side * 0.92, side * 0.92),
                     outline=colour, width=width)
        draw.arc((side * 0.34, side * 0.22, side * 0.66, side * 0.56), 180, 20,
                 fill=colour, width=width)
        draw.line([(side / 2, side * 0.56), (side / 2, side * 0.66)],
                  fill=colour, width=width)
        draw.ellipse((side * 0.44, side * 0.74, side * 0.56, side * 0.86), fill=colour)
    else:  # dot
        draw.ellipse((side * 0.22, side * 0.22, side * 0.78, side * 0.78), fill=colour)

    image = image.resize((size, size), Image.LANCZOS)
    _PIL_CACHE[key] = image
    return ctk.CTkImage(light_image=image, dark_image=image, size=(size, size))


def status_colour(status: str) -> str:
    return {
        "converted": Palette.success,
        "skipped": Palette.warning,
        "error": Palette.danger,
        "cancelled": Palette.text_faint,
    }.get(status, Palette.text_muted)


ICON_FOR_KIND = {
    "info": "info",
    "question": "question",
    "warning": "warn",
    "error": "close",
    "success": "check",
}
