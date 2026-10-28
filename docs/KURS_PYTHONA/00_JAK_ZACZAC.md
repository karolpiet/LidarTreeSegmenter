# Jak zacząć – zanim otworzysz pierwszą lekcję

Ten kurs uczy Pythona na prawdziwym kodzie programu **LidarTreeSegmenter** – tego samego, który
liczy pierśnice, wysokości i miąższość ze skanów TLS. Nie musisz nic umieć.
Wystarczy, że umiesz otworzyć folder w Eksploratorze Windows.

Każda lekcja to trzy pliki:

| plik | co to jest |
|---|---|
| `lekcja_NN_temat.md` | tekst do czytania (ten, który właśnie czytasz, jest taki sam) |
| `cwiczenie_NN_temat.py` | program z dziurami do uzupełnienia (miejsca **TODO**) |
| `rozwiazanie_NN_temat.py` | gotowy, działający program – zajrzyj, gdy utkniesz |

Są jeszcze:

- `kurs_wspolne.py` – nasza „skrzynka z narzędziami” (używamy jej od lekcji 6),
- `dane_testowe\make_maly_las.py` – wycina mały kawałek skanu, żeby ćwiczenia szły szybko,
- `OTWORZ_KONSOLE_TUTAJ.bat` – otwiera czarne okno konsoli od razu w folderze kursu,

---

## 1. Gdzie leży kurs

Kurs leży w folderze programu:

```
C:\...\LidarTreeSegmenter\docs\KURS_PYTHONA\
```

Wyniki skanów (pliki, na których ćwiczymy) leżą tu:

```
C:\...\LidarTreeSegmenter\wyniki\<nazwa_skanu>\02_CHMURY\
    <nazwa_skanu>_segmenty.laz   ← każdy punkt ma numer drzewa i wysokość nad gruntem
    <nazwa_skanu>_czesci.laz     ← każdy punkt ma numer drzewa i część: pień / gałęzie / liście
```

---

## 2. Konsola – czarne okno, w którym uruchamiamy programy

**Konsola** (wiersz polecenia, `cmd`) to okno, w którym wpisujesz polecenia zamiast klikać.
Wygląda groźnie, ale potrzebujemy z niej tylko jednego polecenia: `python`.

### Najprostszy sposób

Kliknij dwa razy plik **`OTWORZ_KONSOLE_TUTAJ.bat`** w folderze kursu.
Otworzy się czarne okno, które „stoi” już w folderze kursu.

### Sposób ręczny (warto znać)

1. Otwórz folder `KURS_PYTHONA` w Eksploratorze.
2. Kliknij w **pasek adresu** u góry okna (tam, gdzie jest ścieżka).
3. Wpisz `cmd` i naciśnij **Enter**.

W oknie zobaczysz coś takiego:

```
C:\...\LidarTreeSegmenter\docs\KURS_PYTHONA>
```

To jest **znak zachęty**. Mówi: „jestem w tym folderze i czekam na polecenie”.

### Sprawdź, czy Python działa

Wpisz i naciśnij Enter:

```
python --version
```

Powinno pokazać np. `Python 3.12.4`. Jeśli pojawi się komunikat, że polecenie
nie zostało rozpoznane – uruchom raz `ZAINSTALUJ_RAZ.bat` z folderu LidarTreeSegmenter albo
zainstaluj Pythona ze strony python.org (zaznacz „Add Python to PATH”).

---

## 3. Uruchamianie programu `.py`

Program w Pythonie to zwykły plik tekstowy z końcówką `.py`. Uruchamiasz go tak:

```
python rozwiazanie_01_podstawy.py
```

Większość lekcji potrzebuje jeszcze **ścieżki do pliku ze skanem**. Dopisujesz ją po spacji:

```
python rozwiazanie_03_laspy.py ..\..\wyniki\SKAN\02_CHMURY\SKAN_czesci.laz
```

`..\..\` znaczy „dwa foldery wyżej” – z `KURS_PYTHONA` do `docs`, potem do `LidarTreeSegmenter`.

> **Sztuczka, która oszczędza mnóstwo pisania:** wpisz `python rozwiazanie_03_laspy.py`
> i **spację**, a potem **przeciągnij plik `.laz` myszką z Eksploratora do czarnego okna**.
> Windows sam wpisze pełną ścieżkę (czasem w cudzysłowie – to dobrze). Naciśnij Enter.

Inne przydatne rzeczy w konsoli:

| co chcesz zrobić | co wpisać / nacisnąć |
|---|---|
| powtórzyć poprzednie polecenie | strzałka **↑** |
| przerwać program, który liczy za długo | **Ctrl + C** |
| zobaczyć pliki w folderze | `dir` |
| wejść do podfolderu | `cd dane_testowe` |
| wrócić folder wyżej | `cd ..` |
| wyczyścić okno | `cls` |

Programy z kursu zapisują swoje wyniki (obrazki, tabele, chmury) do folderu
**`wyniki_kursu`**, który same tworzą w folderze, w którym stoi konsola.

---

## 4. Mały kawałek skanu do ćwiczeń (`dane_testowe`)

Prawdziwy skan ma **15 milionów punktów i więcej**. Programy z kursu poradzą sobie z nim
(trwa to od kilku sekund do minuty, potrzeba ok. 2 GB pamięci), ale do nauki wygodniej
mieć mały plik. Program `dane_testowe\make_maly_las.py` wycina kwadrat 6 × 6 m:

```
cd dane_testowe
python make_maly_las.py ..\..\..\wyniki\SKAN\02_CHMURY\SKAN_czesci.laz 2.4 -3.5
cd ..
```

- `2.4 -3.5` to współrzędne X i Y środka kwadratu – np. pozycja ładnego drzewa.
  Pozycje drzew są w tabeli `wyniki\SKAN\03_TABELE\SKAN_czesci_drzewa.csv`
  (kolumny `pozycja_x` i `pozycja_y` – otwórz ją w Excelu).
- Bez współrzędnych program wytnie kwadrat ze środka skanu.
- Czwarta liczba zmienia bok kwadratu, np. `... 2.4 -3.5 10` → 10 × 10 m.

Powstanie plik `dane_testowe\SKAN_czesci_maly_2_-4.laz` (ok. 1 mln punktów, kilka MB).
Wszystkie pola zostają (numer drzewa, część, wysokość), więc lekcje działają na nim
dokładnie tak samo jak na całym skanie – tylko kilka razy szybciej.

> Wytnij dwa pliki z tego samego miejsca: z `_segmenty.laz` i z `_czesci.laz`.
> Pierwszy ma **wysokość nad gruntem**, drugi ma **części drzewa** (pień, gałęzie, liście).

---

## 5. Gdzie edytować programy

Plik `.py` można otworzyć w dowolnym edytorze tekstu. Nie używaj Worda – psuje tekst.

| edytor | zalety | jak otworzyć plik |
|---|---|---|
| **IDLE** (jest razem z Pythonem) | nic nie trzeba instalować; **F5** uruchamia program | prawy klik na plik → *Edit with IDLE* |
| **Notepad++** | lekki, koloruje kod | prawy klik → *Edit with Notepad++* |
| **VS Code** | najwygodniejszy na dłużej, podpowiada błędy | *Plik → Otwórz folder…* → `KURS_PYTHONA` |

**Uwaga na IDLE i F5:** IDLE nie pyta o ścieżkę do skanu, więc programy, które jej
potrzebują, zakończą się komunikatem „nie podano pliku”. Edytuj w IDLE, a uruchamiaj
w konsoli. (W VS Code możesz uruchamiać w terminalu na dole okna – to też jest konsola.)

**Zasady pisania w Pythonie, o które najczęściej się potykamy:**

1. **Wcięcia mają znaczenie.** Linie „w środku” pętli `for` albo warunku `if` muszą być
   przesunięte o **4 spacje**. Nie mieszaj spacji i tabulatorów.
2. **Wielkość liter ma znaczenie.** `Drzewo` i `drzewo` to dwie różne zmienne.
3. **Liczby z kropką, nie przecinkiem:** `1.3`, a nie `1,3`. Przecinek oddziela elementy listy.
4. **Polskie litery** wolno pisać w tekstach i komentarzach. W nazwach zmiennych lepiej ich
   unikać (`piersnica`, nie `pierśnica`) – tak robi też LidarTreeSegmenter.
5. Wszystko po znaku `#` to **komentarz** – Python go pomija. Pisz komentarze dla siebie!

---

## 6. Komunikat o błędzie (Traceback) – jak go czytać

Błędy są normalne. Każdy programista widzi je sto razy dziennie. Python mówi dokładnie,
co mu się nie podoba – trzeba tylko wiedzieć, gdzie patrzeć.

Przykład:

```
Traceback (most recent call last):
  File "C:\...\...\KURS_PYTHONA\cwiczenie_02_numpy.py", line 41, in <module>
    print(z.min())
          ^^^^^
AttributeError: 'NoneType' object has no attribute 'min'
```

Czytamy **od dołu**:

1. **Ostatnia linia** – rodzaj błędu i opis. Tu: `AttributeError` – „obiekt `None` nie ma
   czegoś takiego jak `min`”. Czyli zmienna `z` jest pusta (`None`), bo nie uzupełniliśmy TODO.
2. **Linia wyżej** – fragment kodu, w którym wystąpił błąd (`print(z.min())`),
   a daszki `^^^^^` pokazują dokładne miejsce.
3. **`File ..., line 41`** – nazwa pliku i **numer linii**. Otwórz plik w edytorze i idź do
   tej linii (w IDLE: *Edit → Go to Line*, w VS Code: **Ctrl + G**).

Gdy Traceback ma kilka bloków `File ...`, to znaczy, że funkcja wywołała funkcję.
Najważniejszy jest zwykle **ostatni blok, który dotyczy Twojego pliku**.

Najczęstsze błędy na początku:

| błąd | co znaczy | co zrobić |
|---|---|---|
| `SyntaxError: invalid syntax` | literówka w kodzie: brak `:` po `if`/`for`/`def`, brak nawiasu | sprawdź wskazaną linię i tę **przed nią** |
| `IndentationError` | złe wcięcie | wyrównaj linie do 4 spacji |
| `NameError: name 'x' is not defined` | używasz zmiennej, której nie ma (literówka?) | sprawdź pisownię i wielkość liter |
| `ModuleNotFoundError: No module named 'laspy'` | brak biblioteki | `python -m pip install laspy lazrs` |
| `ModuleNotFoundError: No module named 'kurs_wspolne'` | konsola stoi w innym folderze niż lekcja | uruchamiaj z folderu `KURS_PYTHONA` |
| `FileNotFoundError` | nie ma takiego pliku | sprawdź ścieżkę; przeciągnij plik do konsoli |
| `IndexError: index 5 is out of bounds` | sięgasz po element, którego nie ma (lista ma mniej elementów) | pamiętaj: liczymy **od zera** |
| `MemoryError` | za mało pamięci | użyj małego pliku z `dane_testowe` |

Komunikaty zaczynające się od `BŁĄD:` (po polsku) wypisują nasze programy same –
mówią, czego brakuje, i co wpisać.

---

## 7. Plan nauki

Rób lekcje po kolei. Na każdą przeznacz wieczór:

1. przeczytaj `lekcja_NN_….md`,
2. uruchom `rozwiazanie_NN_….py` i popatrz, co wypisuje,
3. otwórz `cwiczenie_NN_….py`, uzupełnij TODO, uruchamiaj po każdej zmianie,
4. porównaj z rozwiązaniem.

Spis lekcji jest w pliku `SPIS_TRESCI.md`. Powodzenia!
