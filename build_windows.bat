@echo off
REM ===========================================================================
REM  Budowanie programu dla Windows.
REM
REM  Uruchom z tego katalogu:  build_windows.bat
REM
REM  Skrypt celowo zatrzymuje sie przy pierwszym bledzie i mowi, co jest nie
REM  tak. Bez tego najczestszym efektem jest "mignelo okno i nic sie nie stalo".
REM ===========================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo.
echo ============================================================
echo  1/4  Sprawdzenie wersji Pythona
echo ============================================================
python -c "import sys,struct; v=sys.version_info; bits=struct.calcsize('P')*8; ok = bits==64 and (3,10)<=v[:2]<=(3,14); print('Python %d.%d %d-bit' % (v.major, v.minor, bits)); sys.exit(0 if ok else 1)"
if errorlevel 1 (
    echo.
    echo BLAD: potrzebny jest Python 3.10-3.14 w wersji 64-bit.
    echo Sprawdz, co masz zainstalowane:  py -0
    echo Dla paczek z katalogu wheels/ wymagany jest Python 3.11.
    exit /b 1
)

echo.
echo ============================================================
echo  2/4  Instalowanie zaleznosci
echo ============================================================
if exist "wheels\*.whl" (
    echo Instaluje z katalogu wheels - bez internetu, bez kompilowania.
    python -m pip install --no-index --find-links wheels -r requirements.txt pyinstaller
) else (
    echo UWAGA: brak katalogu wheels\ - instaluje z internetu.
    python -m pip install -r requirements.txt pyinstaller
)
if errorlevel 1 (
    echo.
    echo BLAD: nie udalo sie zainstalowac zaleznosci.
    echo Jesli widzisz "MSYS2 not found" - Twoj Python nie ma gotowej paczki
    echo pi-heif. Uzyj Pythona 3.11 64-bit albo pobierz wlasne paczki do wheels/
    echo (instrukcja w wheels\README.txt).
    exit /b 1
)

echo.
echo ============================================================
echo  3/4  Testy
echo ============================================================
python -m pytest -q
if errorlevel 1 (
    echo.
    echo BLAD: testy nie przechodza - nie buduje programu z bledem.
    exit /b 1
)

echo.
echo ============================================================
echo  4/4  Budowanie pliku .exe
echo ============================================================
if not exist "assets\app.ico" (
    echo Generuje ikone...
    python tools_generate_icon.py
)
python -m PyInstaller heic2jpg.spec --noconfirm --distpath dist --workpath build
if errorlevel 1 (
    echo.
    echo BLAD: PyInstaller nie zakonczyl pracy.
    exit /b 1
)

echo.
echo Sprawdzam zbudowany program...
dist\HEIC-to-JPG-Converter.exe --diagnostic --test-file tests\fixtures\photo_small.heic
if not exist "dist\diagnostyka.txt" (
    echo.
    echo BLAD: program nie zapisal raportu - nie uruchomil sie poprawnie.
    exit /b 1
)
findstr /C:"WNIOSEK: srodowisko wyglada dobrze." dist\diagnostyka.txt >nul
if errorlevel 1 (
    echo.
    echo UWAGA: raport diagnostyczny zglasza problem - przeczytaj dist\diagnostyka.txt
    type dist\diagnostyka.txt
    exit /b 1
)

echo.
echo Kopiuje pliki konfiguracyjne obok programu...
copy /y config.py dist\config.py >nul
if exist legal xcopy /y /i /q legal dist\legal >nul

echo.
echo ============================================================
echo  GOTOWE
echo ============================================================
echo  Program:  dist\HEIC-to-JPG-Converter.exe
echo.
echo  Przed wydaniem:
echo    - uzupelnij SUPPORT_URL w config.py (link do buycoffee.to)
echo    - sprawdz SERVER_URL
echo    - uzupelnij pola [POLA] w legal\EULA-HEIC-to-JPG-Converter.txt
echo ============================================================
endlocal
