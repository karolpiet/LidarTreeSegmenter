# Lekcja 3 – Czytamy plik .las / .laz biblioteką laspy

**Czego się nauczysz:** co jest w pliku `.las` / `.laz`, jak odczytać nagłówek, współrzędne
x, y, z i **pola dodatkowe**, które dopisuje LidarTreeSegmenter (`treeID`, `czesc`, `wys_nad_grunt`),
oraz jak napisać program, który działa także na surowym skanie bez tych pól.

**Pliki:** `cwiczenie_03_laspy.py`, `rozwiazanie_03_laspy.py`

---

## Najpierw po leśnemu

Plik `.las` jest jak **operat taksacyjny**:

- na początku jest **strona tytułowa** (nagłówek): ile punktów, jaki obszar, w jakich
  jednostkach – można ją przeczytać, nie kartkując całości,
- potem idą **opisy taksacyjne** – tu: punkty, jeden po drugim; każdy punkt ma stałe
  rubryki (x, y, z, intensywność, czas GPS…),
- a LidarTreeSegmenter dopisuje **własne rubryki**: numer drzewa, część drzewa, wysokość nad gruntem.
  To jak dopisanie ołówkiem na marginesie kolumny „uwagi”.

`.laz` to ten sam `.las`, tylko **spakowany** (jak `.zip`) – zwykle 5–10 razy mniejszy.
laspy rozpakowuje go sam, potrzebuje do tego biblioteki `lazrs`.

---

## Skala i przesunięcie – dlaczego x to nie zawsze to, co w pliku

Żeby plik był mały, współrzędne zapisuje się jako **liczby całkowite**, np. `X = 20203`.
Prawdziwe metry dostajemy wzorem:

```
x [m] = X · skala + przesunięcie      np.  20203 · 0.001 + (−20.0) = 0.203 m
```

Skala `0.001` znaczy: dokładność zapisu 1 mm. laspy liczy to za nas:

- `las.X` (wielka litera) – surowe liczby całkowite z pliku,
- `las.x` (mała litera) – gotowe metry. **Zawsze używaj małych liter.**

---

## Najważniejsze polecenia laspy

```python
import laspy

# 1. tylko nagłówek – szybko, nie czyta punktów
with laspy.open("skan.laz") as plik:
    print(plik.header.point_count)   # liczba punktów
    print(plik.header.mins)          # [x_min, y_min, z_min]
    print(plik.header.maxs)

# 2. cały plik do pamięci
las = laspy.read("skan.laz")
pola = list(las.point_format.dimension_names)        # nazwy wszystkich rubryk
dodatkowe = list(las.point_format.extra_dimension_names)   # tylko te dopisane
x = np.asarray(las.x)                                # współrzędne w metrach
drzewo = np.asarray(las["treeID"])                   # pole dodatkowe po nazwie
```

`with ... as plik:` to „otwórz, zrób swoje, i **zamknij sam**, nawet gdy coś pójdzie źle”.

### Pola, które dopisuje LidarTreeSegmenter

| plik | pole | znaczenie |
|---|---|---|
| `<skan>_segmenty.laz` | `treeID_pred` | numer drzewa (0 = punkt bez drzewa, np. grunt) |
| | `wys_nad_grunt` | wysokość punktu nad gruntem [m] |
| `<skan>_czesci.laz` | `treeID` | numer drzewa |
| | `czesc` | 0 nic, 1 pień, 2 gałęzie, 3 liście, 4 podszyt |
| | `p_drewno` | 0…1 – jak bardzo punkt wygląda na drewno |

### Program odporny na brak pól

Surowy skan prosto ze skanera nie ma tych pól. Dlatego zawsze **sprawdzamy, zanim sięgniemy**:

```python
if "czesc" in pola:
    czesc = np.asarray(las["czesc"])
else:
    print("Brak pola czesc - to surowy skan.")
```

Bez tego sprawdzenia Python zakończy się błędem przy próbie odczytu nieistniejącego pola.

### Liczenie: `np.unique` i `np.bincount`

```python
numery = np.unique(drzewo[drzewo > 0])        # różne numery drzew (bez zera)
ile = np.bincount(czesc, minlength=5)         # ile punktów ma kod 0, 1, 2, 3, 4
```

`np.bincount` to jak liczenie drzew na kartce kreskami w rubrykach 0, 1, 2, 3, 4.

---

## Prawdziwy kod LidarTreeSegmenter – linijka po linijce

Fragment z `program\40_widok_3d.py` (budowa widoku 3D w przeglądarce):

```python
    print(f"[WIDOK 3D] Wczytuję {p_cz.name}", flush=True)
    las = laspy.read(str(p_cz))
    xyz = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                           np.asarray(las.z)])
    drzewo = np.asarray(las.treeID).astype(np.int64)
    czesc = np.asarray(las.czesc).astype(np.uint8)
```

| linia | co robi |
|---|---|
| `print(..., flush=True)` | wypisz komunikat **od razu** (bez `flush` czasem pojawia się z opóźnieniem, gdy program długo liczy) |
| `las = laspy.read(str(p_cz))` | wczytaj cały plik `_czesci.laz`. `p_cz` to ścieżka (obiekt `Path`), `str()` zamienia ją na tekst |
| `np.column_stack([...])` | tablica N × 3 – już znasz z lekcji 2 |
| `las.treeID` | pole dodatkowe można czytać też „przez kropkę”, jak zwykłe pole |
| `.astype(np.uint8)` | `czesc` ma tylko wartości 0–4, więc wystarczy najmniejszy typ: 1 bajt na punkt. Przy 15 mln punktów to 15 MB zamiast 120 MB – **oszczędzanie pamięci** |

A tak opisuje plik `.laz` sam `tree_segmenter_tool\02_detect_trees.py` (krok 1):

```python
    Co to jest .laz:
        To spakowany .las - standardowy format chmur punktow. Wewnatrz
        wspolrzedne sa trzymane jako liczby calkowite plus wspolczynnik skali,
        zeby plik byl mniejszy. laspy rozpakowuje to za nas: las.x, las.y, las.z
        daja juz gotowe metry.
```

Zwróć uwagę: w LidarTreeSegmenter przed odczytem pola sprawdzane jest, czy ono istnieje
(`pole_drzewa = next((p for p in POLA_DRZEWA if p in pola), None)` – lekcja 1).
Widok 3D tego nie robi, bo wcześniej sprawdza, czy w ogóle jest plik `_czesci.laz`.

---

## Uruchom rozwiązanie

```
python rozwiazanie_03_laspy.py ..\..\wyniki\SKAN\02_CHMURY\SKAN_czesci.laz
```

Przykładowy wynik (wycinek 6 × 6 m z prawdziwego skanu):

```
=== NAGŁÓWEK ===
Wersja LAS:      1.4
Format punktów:  6
Liczba punktów:  1 069 021
Skala (dokładność zapisu): [0.001 0.001 0.001] m
Przesunięcie (offset):     [-20. -20.  -3.]
...
Pola dodatkowe (dopisane przez program): treeID, czesc, p_drewno

Pierwszy punkt: x=0.203  y=-0.953  z=-0.493
Surowa liczba całkowita X w pliku: 20203  (= (0.203 - offset) / skala)
Prostokąt skanu: 6.0 × 6.0 m = 0.004 ha
Gęstość: 29 705 pkt/m²

Numer drzewa w polu 'treeID': 6 drzew (numery 14 .. 54)
Najwięcej punktów ma drzewo 43: 420 343

Podział na części (pole 'czesc'):
  0 nic (grunt / bez drzewa)       151 915 pkt  ( 14.2%)
  1 pień                            77 839 pkt  (  7.3%)
  2 gałęzie                        274 903 pkt  ( 25.7%)
  3 liście / igły                  272 009 pkt  ( 25.4%)
  4 podszyt                        292 355 pkt  ( 27.3%)
```

Na całym skanie 15 mln punktów wczytanie trwa kilka sekund. Uruchom też na surowym
skanie (bez pól LidarTreeSegmenter) – program powie „brak – to surowy skan” zamiast się wysypać.

---

## Ćwiczenie

W `cwiczenie_03_laspy.py`:

1. **TODO 1** – jeśli nie podano pliku, zakończ program jasnym komunikatem (`sys.exit("BŁĄD: ...")`).
2. **TODO 2** – wypisz zasięg z nagłówka (`nag.mins`, `nag.maxs`).
3. **TODO 3** – wytnij x, y, z i wypisz pierwszy punkt.
4. **TODO 4** – policz drzewa (`np.unique`).
5. **TODO 5** – policz punkty pnia, gałęzi i liści (`np.bincount`).

**Dla chętnych:** policz, jaki procent punktów każdego drzewa to pień
(`(czesc[drzewo == 17] == 1).mean()`).

## Podpowiedź

- `sys.exit("tekst")` wypisuje tekst i kończy program.
- Pole może się nazywać `treeID` albo `treeID_pred` – sprawdź oba:
  `pole = "treeID" if "treeID" in pola else "treeID_pred"`.
- Zera w numerze drzewa to punkty bez drzewa – odfiltruj je: `drzewo[drzewo > 0]`.
- Jeśli widzisz `laspy.errors.LaspyException: No LazBackend` – doinstaluj
  `python -m pip install lazrs`.

## Podsumowanie

- `laspy.open(...)` – sam nagłówek (szybko), `laspy.read(...)` – wszystko,
- `las.x / las.y / las.z` – metry; `las.X` – surowe liczby całkowite,
- pola dodatkowe: `las["treeID"]`; zawsze sprawdzaj `if "pole" in pola`,
- `np.unique` – różne wartości, `np.bincount` – ile razy każda.
