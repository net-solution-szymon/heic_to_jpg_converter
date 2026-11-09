GOTOWE PACZKI DLA WINDOWS
=============================================================================

Ten katalog zawiera wszystkie biblioteki potrzebne do zbudowania programu,
w wersjach dla:

    Windows 64-bit (win_amd64)  +  Python 3.11

Dzieki temu budowanie NIE wymaga internetu ani kompilatora:

    python -m pip install --no-index --find-links wheels -r requirements.txt pyinstaller

Opcja --no-index calkowicie odcina siec, wiec nie moze sie zdarzyc sytuacja,
w ktorej pip probuje kompilowac cos ze zrodel (np. pi-heif bez gotowej paczki
konczy sie bledem "MSYS2 not found").

Co jest w srodku (22 paczki, ok. 16 MB):
    pi_heif, pillow              - obsluga obrazow i HEIC (paczki natywne)
    customtkinter, darkdetect    - wyglad interfejsu
    tkinterdnd2                  - przeciaganie plikow
    httpx, httpcore, anyio, ...  - wysylka statystyk
    pyinstaller, altgraph, ...   - budowanie pliku .exe
    pytest, pluggy, ...          - testy

JEZELI MASZ INNEGO PYTHONA NIZ 3.11
-----------------------------------
Te paczki NIE zadzialaja z Pythonem 3.10, 3.12-3.14, 32-bitowym ani na
Windows ARM. Wtedy pobierz wlasne:

    python -m pip download -r requirements.txt pyinstaller --dest wheels ^
        --only-binary=:all: --platform win_amd64 --python-version 3.11 ^
        --implementation cp --abi cp311

(zmien 3.11/cp311 na swoja wersje). Sprawdz najpierw, co masz:  py -0

NIE DODAWAJ tych paczek do repozytorium na GitHubie, jesli nie chcesz trzymac
16 MB binariow - usun katalog wheels/ i zainstaluj z internetu:

    python -m pip install -r requirements.txt pyinstaller
