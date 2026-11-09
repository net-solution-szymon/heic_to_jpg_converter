# HEIC → JPG Converter (wersja darmowa, wspierana darowiznami)

Konwerter zdjęć HEIC z iPhone'a na JPG. Bez licencji, bez limitów, bez
rejestracji. Program prosi o dobrowolne wsparcie po wykonanej pracy i wysyła
anonimowe statystyki, żeby było wiadomo, ile osób go używa.

To **osobny projekt** — powstał obok wersji z licencjonowaniem i nie zmienia
tamtego kodu.

---

## 1. Uruchomienie ze źródeł

```bat
python -m pip install -r requirements.txt
python main.py
```

Sprawdzenie środowiska bez otwierania okna (przydatne przy problemach):

```bat
python main.py --diagnostic
python main.py --diagnostic --test-file zdjecie.HEIC
```

Testy:

```bash
xvfb-run -a python -m pytest      # Linux bez pulpitu
python -m pytest                  # Windows / pulpit
```

---

## 2. Mapa projektu (do czytania i debugowania)

```
main.py                 punkt wejścia, diagnostyka, obsługa awarii
config.py               WSZYSTKO, co się ustawia przed wydaniem
heic2jpg/
    app.py              okno programu (jedyny duży plik - interfejs)
    converter.py        silnik konwersji HEIC → JPG (nie zależy od UI)
    support.py          licznik konwersji i prośba o wsparcie
    telemetry.py        anonimowe statystyki i wiadomość do autora
    about.py            okna: o programie, licencja, noty, prywatność, kontakt
    store.py            pamięć programu (jeden plik JSON w katalogu użytkownika)
    dialogs.py          własne okna dialogowe
    theme.py            kolory, czcionki, ikony
    window.py           połączenie customtkinter z tkinterdnd2
legal/                  EULA i noty bibliotek (pokazywane w programie)
tests/                  testy: store, wsparcie, telemetria, silnik, interfejs
```

Trzy moduły czyta się jak opis działania programu: `support.py`, `telemetry.py`
i `store.py`. Reszta to interfejs i silnik.

---

## 3. Prośba o wsparcie — jak działa

Prośba pojawia się **tylko** gdy spełnione są oba warunki:

* użytkownik przekonwertował **50 plików** (i kolejne 50 przed każdą następną
  prośbą — czyli 50, 100, 150…),
* od poprzedniej prośby minęło **30 dni**.

Do tego:

* nigdy nie blokuje pracy — to zwykłe okno z wyjściem,
* „Nie pokazuj więcej" i „Już wsparłem" są **trwałe**,
* zamknięcie okna (X / Escape) to tylko odroczenie, nie wyciszenie na zawsze,
* pozycja **„Postaw kawę"** jest zawsze dostępna w nagłówku i w menu Pomoc.

Zmiana progów — `config.py`:

```python
PROMPT_AFTER_FILES = 50
PROMPT_COOLDOWN_DAYS = 30
```

Adres wsparcia (wymagany, inaczej przycisk powie, że nie jest ustawiony):

```python
SUPPORT_URL = "https://buycoffee.to/twojanazwa"
GITHUB_URL = ""     # opcjonalnie - pokazywany w oknie „O programie" i w licencji
```

Program **nie obsługuje płatności**. Otwiera stronę wsparcia w przeglądarce.

---

## 4. Statystyki — co jest wysyłane

Wysyłane (raz na 24 godziny): losowy identyfikator instalacji, wersja programu,
system i wersja systemu, łączna liczba konwertowanych plików.

**Nie jest wysyłane:** nazwy ani zawartość zdjęć, ścieżki, nazwa użytkownika ani
komputera, żaden identyfikator sprzętu (numer dysku, MAC, UUID płyty).
Identyfikator instalacji to zwykły losowy UUID — nie wynika z niczego,
co jest w komputerze.

Użytkownik dowiaduje się o tym przy pierwszym uruchomieniu i może wyłączyć
wysyłkę od razu albo później w **Pomoc → Prywatność i statystyki**.
Po wyłączeniu program nie łączy się z serwerem ani razu.

Dane programu leżą w jednym pliku:

```
Windows:  %APPDATA%\HEIC2JPG\data.json
Linux:    ~/.config/heic2jpg/data.json
```

Usunięcie tego pliku kasuje też identyfikator instalacji.

Adres serwera:

```python
SERVER_URL = "https://heictojpg-telemetry.net-solution.pl"
```

Pusty `SERVER_URL` całkowicie wyłącza telemetrię.

### Sieć firmowa i serwer proxy

Program **nie konfiguruje żadnego proxy**. Łączy się bezpośrednio, tak jak
pozwala na to sieć. W sieciach firmowych, w których ruch wychodzi przez serwer
proxy wymagający zalogowania, statystyki i wiadomości po prostu nie dotrą —
i to jest świadoma decyzja, nie przeoczenie.

**Dlaczego tak.** Wcześniejsza wersja odczytywała ustawienia proxy z systemu
i podstawiała je bibliotece sieciowej. Kod sięgał po API Windows, a pomyłka
w zarządzaniu pamięcią skończyła się uszkodzeniem sterty i natychmiastowym
zamykaniem programu na komputerze użytkownika (kod wyjątku `0xc0000374`).
Funkcja „wyślij anonimowe statystyki" nie jest warta takiego ryzyka. Dlatego
tamten kod usunięto w całości.

Obsługa logowania do firmowego proxy (NTLM, Kerberos) wymagałaby dołożenia
dużej zewnętrznej biblioteki i dostępu do poświadczeń użytkownika. Świadomie
z tego rezygnujemy.

**Co program robi zamiast tego.** Gdy wysłanie wiadomości się nie uda,
użytkownik dostaje konkretny powód i wie, co może zrobić — w tym propozycję
połączenia bez VPN oraz adres e-mail jako drugą drogę kontaktu.

**Uwaga:** statystyki wysyłają się po cichu, więc ich brak nie zakłóca pracy
programu. Konwersja zdjęć działa bez internetu i jest od tego całkowicie
niezależna.

---

## 5. Budowanie pliku .exe (Windows)

`.exe` trzeba zbudować **na Windows** — PyInstaller nie kompiluje krzyżowo.

```bat
python -m pip install --no-index --find-links wheels -r requirements.txt pyinstaller
python -m pytest
python -m PyInstaller heic2jpg.spec --noconfirm
```

Wynik: `dist\HEIC-to-JPG-Converter.exe`.

Po zbudowaniu **skopiuj obok pliku .exe**:

* `config.py` — żeby można go było zmienić bez przebudowywania programu,
* katalog `legal/` — jest w środku programu, ale trzymanie kopii obok nie szkodzi.

Sprawdzenie zbudowanego programu:

```bat
dist\HEIC-to-JPG-Converter.exe --diagnostic
```

Program bez konsoli zapisuje wynik do `diagnostyka.txt` obok siebie.

---

## 6. Gdy coś nie działa

| Objaw | Przyczyna | Co zrobić |
|---|---|---|
| `pip install pi-heif` → `MSYS2 not found` | brak gotowej paczki dla Twojego Pythona, pip próbuje kompilować | użyj Pythona 3.11 64-bit albo instaluj z katalogu `wheels` |
| Okno mignęło i zniknęło | brakuje biblioteki albo błąd przy starcie | uruchom z konsoli: `python main.py`; sprawdź `blad-startu.txt` |
| Brak obsługi HEIC | nie zainstalował się `pi-heif` | `python main.py --diagnostic` pokaże, czego brakuje |
| Nie widać okna, a proces działa | okno zostało ukryte przez bibliotekę | program sam je przywraca po 250 ms; jeśli nie — zgłoś to jako błąd |

Zasada, której trzyma się `main.py`: **program nigdy nie kończy się po cichu**.
Każdy nieudany start pokazuje okno z wyjaśnieniem i zapisuje `blad-startu.txt`.

---

## 7. Licencja i biblioteki

* Tekst licencji: `legal/EULA-HEIC-to-JPG-Converter.txt` (uzupełnij pola `[POLA]`),
* noty bibliotek: `legal/THIRD-PARTY-NOTICES.txt`,
* oba są czytelne z programu: **Pomoc → Licencja** i **Pomoc → Biblioteki**.

Użyte biblioteki: Pillow (MIT-CMU), pi-heif (LGPL-3.0, celowo bez `libx265`
z licencją GPL-2.0), customtkinter (MIT), tkinterdnd2 (MIT), httpx (BSD).
