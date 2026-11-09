"""Generuje ikone aplikacji (assets/app.ico) oraz ikone instalatora.

Ikona jest rysowana programowo, tak samo jak ikony w interfejsie, dlatego:
  * nie ma tu zadnego gotowego pliku graficznego z zewnatrz,
  * nie ma obowiazkow licencyjnych z tytulu grafiki,
  * wyglad jest spojny z oknem programu.

Uruchomienie:  python tools_generate_icon.py
Wynik:         assets/app.ico, assets/app_256.png
"""
from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw

ACCENT_TOP = (86, 148, 255)
ACCENT_BOTTOM = (56, 104, 214)
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def draw_icon(size: int = 1024) -> Image.Image:
    """Rysuje ikone w wysokiej rozdzielczosci (potem zmniejszana z antyaliasingiem)."""
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # --- tlo: zaokraglony kwadrat z pionowym gradientem ---
    radius = int(size * 0.22)
    background = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(background)
    for y in range(size):
        ratio = y / max(1, size - 1)
        colour = tuple(
            int(ACCENT_TOP[i] + (ACCENT_BOTTOM[i] - ACCENT_TOP[i]) * ratio)
            for i in range(3)
        )
        bg_draw.line([(0, y), (size, y)], fill=colour + (255,))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1),
                                           radius=radius, fill=255)
    image.paste(background, (0, 0), mask)

    # --- glyph: slonce + dwa szczyty (motyw zdjecia) ---
    white = (255, 255, 255, 255)
    pale = (214, 230, 255, 255)

    # slonce
    sun = size * 0.135
    cx, cy = size * 0.33, size * 0.31
    draw.ellipse((cx - sun, cy - sun, cx + sun, cy + sun), fill=white)

    # tylny szczyt (jasniejszy, dla glebi)
    draw.polygon(
        [(size * 0.12, size * 0.78), (size * 0.42, size * 0.40), (size * 0.66, size * 0.78)],
        fill=pale,
    )
    # przedni szczyt
    draw.polygon(
        [(size * 0.40, size * 0.78), (size * 0.64, size * 0.47), (size * 0.88, size * 0.78)],
        fill=white,
    )
    # linia horyzontu
    draw.rounded_rectangle(
        (size * 0.12, size * 0.775, size * 0.88, size * 0.805),
        radius=int(size * 0.015), fill=white,
    )
    return image


def main() -> None:
    assets = pathlib.Path(__file__).resolve().parent / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    master = draw_icon(1024)
    ico_path = assets / "app.ico"
    master.save(ico_path, format="ICO", sizes=[(s, s) for s in SIZES])
    master.resize((256, 256), Image.LANCZOS).save(assets / "app_256.png")

    print(f"zapisano {ico_path} ({ico_path.stat().st_size} B), rozmiary: {SIZES}")
    print(f"zapisano {assets / 'app_256.png'}")


if __name__ == "__main__":
    main()
