# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for HEIC -> JPG Converter (free, donation-supported).

Build on the platform you are shipping to - a Windows .exe must be built on
Windows, PyInstaller does not cross-compile:

    pip install pyinstaller
    pyinstaller heic2jpg.spec --noconfirm

Result: dist/HEIC-to-JPG-Converter(.exe)

Notes
-----
* ``console=False`` gives a windowed app: no black console window. While
  troubleshooting, set it to True to see tracebacks. The program also writes
  ``blad-startu.txt`` next to itself on any startup failure, which works even
  without a console.
* ``config.py`` is deliberately NOT bundled. Keep it next to the executable so
  the support address or telemetry server can be changed without rebuilding -
  the program looks next to the binary first.
* ``legal/`` IS bundled: the licence and the library notices must travel with
  the program (LGPL requirement), and they are read from the bundle.
* tkinterdnd2 ships the tkdnd Tcl extension as data files; without the
  collect_data_files call the packaged app fails the moment a file is dropped.
"""
import glob
import os
import sysconfig

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = []
datas += collect_data_files("tkinterdnd2")
datas += collect_data_files("customtkinter")

# Licencja i noty bibliotek - musza byc w srodku programu, bo okno "Licencja"
# czyta je z paczki (about.resource_dir -> sys._MEIPASS).
for _name in ("EULA-HEIC-to-JPG-Converter.txt", "THIRD-PARTY-NOTICES.txt"):
    _path = os.path.join("legal", _name)
    if os.path.isfile(_path):
        datas.append((_path, "legal"))
    else:
        print(f"[spec] UWAGA: brak {_path} - okno 'Licencja' pokaze komunikat bledu.")

# Skladowe natywne HEIC (libheif + libde265) z pakietu pi-heif.
#
# Nie ma dla nich gotowego hooka, a same biblioteki leza POZA katalogiem pakietu:
#   * Linux/macOS (auditwheel):  site-packages/pi_heif.libs/
#   * Windows    (delvewheel):   bezposrednio w site-packages
# Bez ponizszego zebrania spakowany program uruchomi sie i wysypie dopiero przy
# pierwszej probie otwarcia pliku HEIC.
_heif_binaries = []
_purelib = sysconfig.get_paths()["purelib"]
for _directory in (_purelib, os.path.join(_purelib, "pi_heif.libs")):
    if not os.path.isdir(_directory):
        continue
    for _pattern in ("libheif*", "libde265*"):
        for _lib in glob.glob(os.path.join(_directory, _pattern)):
            if os.path.isfile(_lib):
                _heif_binaries.append((_lib, "."))

for _lib, _dest in _heif_binaries:
    datas.append((_lib, _dest))

if not _heif_binaries:
    print("[spec] UWAGA: nie znaleziono bibliotek natywnych pi-heif - "
          "spakowany program nie otworzy plikow HEIC.")

# Tcl/Tk shared libraries.
#
# With a python.org / distro Python, PyInstaller finds these on its own. With a
# standalone build (uv, pyenv, conda) they can live outside the paths PyInstaller
# inspects, and the frozen app then dies at startup with
# "ImportError: libtcl9.0.so: cannot open shared object file" - which looks like
# a tkinterdnd2 problem but is really a missing Tcl/Tk runtime.
binaries = []
_libdir = sysconfig.get_config_var("LIBDIR") or ""
for _pattern in ("libtcl*.so*", "libtk*.so*", "tcl*.dll", "tk*.dll"):
    for _lib in glob.glob(os.path.join(_libdir, _pattern)):
        binaries.append((_lib, "."))

hiddenimports = [
    "PIL._tkinter_finder",
    "pi_heif",      # dekoder HEIC (LGPLv3, bez x265 - patrz legal/)
    "_pi_heif",     # modul skompilowany, importowany dynamicznie
    "customtkinter",
    "httpx",
]

# Wlasna ikona pliku .exe.
#
# Bez tego PyInstaller wstawia SWOJA domyslna ikone - na rozdawanym programie
# to blad wizerunkowy (i cudzy znak graficzny). Ikone generuje
# tools_generate_icon.py, wiec nie ma tu zadnego pliku z zewnatrz.
icon_path = "assets/app.ico"
if not os.path.exists(icon_path):
    print(f"[spec] UWAGA: brak {icon_path} - uruchom tools_generate_icon.py "
          f"(zostanie uzyta domyslna ikona PyInstallera)")
    icon_path = None

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Trim the obvious dead weight: pulling in the whole scientific stack by
    # accident is what turns a 25 MB build into 200 MB.
    excludes=[
        "matplotlib", "numpy", "pandas", "scipy", "IPython", "pytest",
        "setuptools", "pip", "unittest", "pydoc_data",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

# --- tryb budowania (potrzebny do diagnozy na komputerach firmowych) ---------
#
# Domyslnie powstaje JEDEN plik .exe. Taka wersja rozpakowuje sie przy kazdym
# uruchomieniu do katalogu tymczasowego i uruchamia sie stamtad. Niektore
# firmowe systemy ochrony reaguja na to jak na program, ktory cos przemyca,
# i potrafia ubic proces bez zadnego komunikatu.
#
# Zeby sprawdzic to bez zmieniania plikow, ustaw zmienna PRZED budowaniem:
#
#   set HEIC2JPG_ONEDIR=1     -> folder zamiast jednego pliku
#   set HEIC2JPG_CONSOLE=1    -> widoczne okno konsoli (wszystkie komunikaty)
#   set HEIC2JPG_NO_UPX=1     -> bez kompresji UPX
#
# Przyklady (Windows, wiersz polecen):
#   pyinstaller heic2jpg.spec --noconfirm
#   set HEIC2JPG_ONEDIR=1 && pyinstaller heic2jpg.spec --noconfirm
#   set HEIC2JPG_ONEDIR=1 && set HEIC2JPG_CONSOLE=1 && pyinstaller heic2jpg.spec --noconfirm
ONEDIR = os.environ.get("HEIC2JPG_ONEDIR", "") == "1"
CONSOLE = os.environ.get("HEIC2JPG_CONSOLE", "") == "1"
USE_UPX = os.environ.get("HEIC2JPG_NO_UPX", "") != "1"

print(f"[spec] tryb: {'FOLDER (onedir)' if ONEDIR else 'JEDEN PLIK (onefile)'} | "
      f"konsola: {'TAK' if CONSOLE else 'nie'} | "
      f"kompresja UPX: {'tak' if USE_UPX else 'NIE'}")

_wspolne = dict(
    name="HEIC-to-JPG-Converter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=USE_UPX,
    upx_exclude=[],
    console=CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

if ONEDIR:
    # Wersja folderowa: program uruchamia sie ze swojego katalogu, niczego nie
    # rozpakowuje do katalogu tymczasowego.
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **_wspolne)
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=USE_UPX,
                   upx_exclude=[], name="HEIC-to-JPG-Converter")
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
              runtime_tmpdir=None, **_wspolne)
