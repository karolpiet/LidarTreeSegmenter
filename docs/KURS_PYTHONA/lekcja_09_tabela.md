# Lekcja 9 – pandas: tabela drzew, miąższość i eksport do Excela

**Czego się nauczysz:** czym jest `DataFrame` (tabela w pandas), jak dodawać kolumny,
grupować (`groupby`) i sumować, jak policzyć pole przekroju **g** i miąższość
**V = g · h · f** (świerk f = 0,47, buk f = 0,51) i zapisać wynik do Excela (`to_excel`).

**Pliki:** `cwiczenie_09_tabela.py`, `rozwiazanie_09_tabela.py`

---

## Najpierw po leśnemu

numpy to kolumny liczb bez nazw. **pandas** to **manualik taksacyjny**: tabela z nazwanymi
kolumnami (`nr`, `gatunek`, `d13_cm`, `h_m`), w której każdy wiersz to drzewo.
Można w niej liczyć jak w Excelu, tylko bez przeciągania formuł:

- nowa kolumna: `df["g_m2"] = π/4 · d²` – policzy się dla wszystkich wierszy,
- **groupby** to jak zestawienie w operacie: „zsumuj G i V **według gatunku**”,
- **to_excel** zapisuje gotową tabelę do pliku `.xlsx`.

### Wzory leśne, których używamy

| wielkość | wzór | jednostka |
|---|---|---|
| pierśnicowe pole przekroju | g = π/4 · d²  (d w metrach!) | m² |
| miąższość grubizny drzewa | V = g · h · f | m³ |
| pierśnicowa liczba kształtu | f: **świerk 0,47**, **buk 0,51** | – |
| zasobność / ha | V_suma / pole powierzchni [ha] | m³/ha |
| pierśnicowe pole przekroju / ha | G = Σg / pole [ha] | m²/ha |

Te same liczby kształtu są w pliku `LidarTreeSegmenter\tablice_miazszosci.csv` – raport LidarTreeSegmenter bierze
je stamtąd i można je podmienić na tablice regionalne.

---

## Podstawy pandas

```python
import pandas as pd

df = pd.DataFrame({
    "gatunek": ["świerk", "buk", "świerk"],
    "d13_cm":  [32.5, 41.0, 18.2],
    "h_m":     [24.1, 26.5, 15.2],
})
print(df)                       # ładnie wydrukowana tabela
df["d13_cm"]                    # jedna kolumna (albo krócej: df.d13_cm)
df["g_m2"] = np.pi / 4 * (df.d13_cm / 100) ** 2          # nowa kolumna
df["f"] = df.gatunek.map({"świerk": 0.47, "buk": 0.51})  # słownik: gatunek -> f
df["v_m3"] = df.g_m2 * df.h_m * df.f
df[df.d13_cm >= 30]             # maska – jak w numpy: tylko grube drzewa
df.sort_values("h_m")           # posortuj
df.groupby("gatunek")[["g_m2", "v_m3"]].sum()             # sumy według gatunku
df.to_excel("tabela.xlsx", index=False)                    # do Excela
df.to_csv("tabela.csv", sep=";", decimal=",", encoding="utf-8-sig")  # CSV dla polskiego Excela
```

- `.map(słownik)` – zamień każdą wartość według słownika (jak tabela przeliczeniowa),
- `sep=";"` i `decimal=","` – polski Excel oczekuje średnika i przecinka,
- `encoding="utf-8-sig"` – żeby Excel poprawnie pokazał „ś”, „ł”, „ó”.

### groupby + agg – z milionów punktów jedna linijka na drzewo

```python
pkt = pd.DataFrame({"treeID": drzewo, "h": h})          # 6 mln wierszy: punkty
drzewa = pkt.groupby("treeID").agg(
    liczba_punktow=("h", "size"),                        # ile punktów
    wysokosc_m=("h", lambda s: s.quantile(0.999)),       # 99,9 percentyl wysokości
)
```

`groupby("treeID")` rozkłada punkty na kupki według numeru drzewa, a `agg` dla każdej
kupki liczy, co chcemy. `lambda s: ...` to **funkcja jednolinijkowa bez nazwy** –
„weź kolumnę `s` i oddaj jej 99,9 percentyl”.

### Pętla po grupach

```python
for nr, grupa in plaster.groupby("treeID"):
    ...   # grupa = mała tabela z punktami plastra jednego drzewa
```

Tak liczymy pierśnicę każdego drzewa okręgiem z lekcji 6.

---

## Prawdziwy kod LidarTreeSegmenter – linijka po linijce

**Fragment 1** – `program\30_raport.py`, miąższość grubizny każdego drzewa:

```python
def miazszosc_grubizny(d_m, h, grupa, tab):
    """V [m³] dla każdego drzewa wg wzoru jego grupy gatunkowej."""
    v = np.full(len(d_m), np.nan)
    for i, (d, hh, gr) in enumerate(zip(d_m, h, grupa)):
        if gr not in tab.index:
            gr = GRUPA_DOMYSLNA if GRUPA_DOMYSLNA in tab.index else tab.index[0]
        w = tab.loc[gr]
        if not (np.isfinite(d) and np.isfinite(hh)):
            continue
        if str(w.wzor).strip() == "potegowy":
            v[i] = float(w.a) * (d * 100) ** float(w.b) * hh ** float(w.c)
        else:
            v[i] = np.pi / 4 * d ** 2 * hh * float(w.f)
    return v
```

| linia | co robi |
|---|---|
| `v = np.full(len(d_m), np.nan)` | kolumna wyników, na start same `nan` („brak liczby”) |
| `for i, (d, hh, gr) in enumerate(zip(...))` | idź po drzewach; `enumerate` daje też numer wiersza `i` |
| `if gr not in tab.index:` | gatunku nie ma w tablicach? → weź grupę domyślną |
| `w = tab.loc[gr]` | wiersz tablicy miąższości dla tego gatunku (pandas: `.loc[nazwa_wiersza]`) |
| `if not (np.isfinite(d) and ...): continue` | brak pierśnicy albo wysokości → pomiń drzewo (zostaje `nan`) |
| `if ... == "potegowy":` | wzór regionalny V = a · dᵇ · hᶜ (d w cm) |
| `else: v[i] = np.pi / 4 * d ** 2 * hh * float(w.f)` | **nasz wzór: V = g · h · f** |

**Fragment 2** – ten sam plik, miąższość zmierzonego odcinka strzały (suma walców ściętych
między kolejnymi okręgami pnia):

```python
    for t, g in okregi.groupby("treeID"):
        g = g.sort_values("wysokosc_m")
        h = g.wysokosc_m.to_numpy()
        d = g[kol].to_numpy()
        if len(h) < 2:
            continue
        dh = np.diff(h)
        ok = dh <= 0.61          # nie przez dziury dłuższe niż 3 przekroje
        a = np.pi / 4 * d ** 2
        v = dh * (a[:-1] + a[1:] + np.sqrt(a[:-1] * a[1:])) / 3
        wynik[int(t)] = float(v[ok].sum())
```

| linia | co robi |
|---|---|
| `for t, g in okregi.groupby("treeID"):` | dla każdego drzewa `t` – jego okręgi pnia `g` |
| `g.sort_values("wysokosc_m")` | od dołu do góry |
| `.to_numpy()` | kolumna pandas → tablica numpy |
| `np.diff(h)` | różnice wysokości kolejnych przekrojów (długości sekcji) |
| `a = π/4 · d²` | pole każdego przekroju |
| `v = dh · (a₁ + a₂ + √(a₁·a₂)) / 3` | objętość **stożka ściętego** między dwoma przekrojami – sekcyjna metoda kubatury |
| `a[:-1]`, `a[1:]` | „wszystkie oprócz ostatniego” i „wszystkie oprócz pierwszego” – pary sąsiednich przekrojów bez pętli |

---

## Uruchom rozwiązanie

```
python rozwiazanie_09_tabela.py ..\..\wyniki\SKAN\02_CHMURY\SKAN_czesci.laz
python rozwiazanie_09_tabela.py ..\..\wyniki\SKAN\02_CHMURY\SKAN_czesci.laz buk
```

Uruchamiaj na pliku **`_czesci.laz`**. Na `_segmenty.laz` pień nie jest oznaczony, więc
w plastrze są krzaki podszytu i prawie każde drzewo dostanie uwagę „okrąg niepewny”
(na naszym skanie pierśnicę dostało tylko 1 drzewo) – to ta sama lekcja co w rozdziale 6.

Drugi argument to gatunek domyślny (gdy obok nie ma tabeli LidarTreeSegmenter z rozpoznanym gatunkiem).
Wynik na całym skanie (ok. 13 s):

```
Drzew: 66
Gatunki wzięte z SKAN_czesci_drzewa.csv

Pierwsze drzewa:
        liczba_punktow  wysokosc_m  d13_cm gatunek   g_m2   v_m3
treeID
1                22954   12.202000     NaN  świerk    NaN    NaN
3                12654    7.476000  49.078  świerk  0.189  0.665
4                68563   19.558001  33.570     buk  0.089  0.883
6                65892   18.056000  38.509  świerk  0.116  0.988
...
Pole prostokąta skanu: 0.160 ha (w przybliżeniu)
         liczba_drzew  srednia_d13_cm  srednia_h_m  G_m2   V_m3  N_na_ha  G_m2_na_ha  V_m3_na_ha
gatunek
buk               8.0           31.21        18.66  0.74   7.02    50.01        4.62       43.85
świerk           25.0           37.93        17.93  3.06  26.89   156.27       19.10      168.10
RAZEM            33.0           36.30        18.11  3.79  33.91   206.28       23.72      211.95

Zapisano: wyniki_kursu\SKAN_czesci_tabela_drzew.xlsx
```

Otwórz plik `.xlsx` w Excelu. W arkuszu „Drzewa” jest kolumna `d13_LidarTreeSegmenter_cm` – pierśnica
z LidarTreeSegmenter, obok naszej. Tam, gdzie obie są, zgadzają się zwykle co do 1–2 cm.

**Bądź krytyczny wobec wyniku** – to najważniejsza umiejętność taksatora:

- Około połowy drzew nie ma naszej pierśnicy (`NaN`). W kolumnie `uwagi` jest dlaczego:
  brak punktów pnia na 1,3 m (pień zasłonięty podszytem) albo okrąg niepewny.
  LidarTreeSegmenter w takich miejscach **dorysowuje pień** z wyższych przekrojów – my tego nie robimy,
  więc nasze G i V/ha są **zaniżone**. Raport LidarTreeSegmenter jest pełniejszy.
- Pole powierzchni liczymy jako prostokąt wokół skanu (40 × 40 m = 0,160 ha), a skan jest
  **kołem** o promieniu 20 m (0,126 ha) – zobaczysz to na mapie w lekcji 10. Wartości na
  hektar są przez to dodatkowo zaniżone o ok. 20%.
- Drzewa niższe niż 5 m (krzewy, podrost, złomy) nie wchodzą do sumy (kolumna `do_sumy`).

---

## Ćwiczenie

W `cwiczenie_09_tabela.py`:

**Część A** (bez skanu – `python cwiczenie_09_tabela.py`):

1. **TODO 1** – kolumna `g_m2`.
2. **TODO 2** – kolumna `f` (świerk 0,47, buk 0,51) przez `.map(...)`.
3. **TODO 3** – kolumna `v_m3`.
4. **TODO 4** – sumy G i V według gatunku.
5. **TODO 5** – zapis do Excela.

**Część B** (ze skanem – `python cwiczenie_09_tabela.py plik.laz`):

6. **TODO 6** – `groupby("treeID")`: liczba punktów i wysokość każdego drzewa.
7. **TODO 7** – 10 najwyższych drzew.

**Dla chętnych:** w rozwiązaniu policz pole koła zamiast prostokąta
(`np.pi * 20**2 / 10000`) i porównaj V/ha z raportem LidarTreeSegmenter (`01_RAPORT\SKAN_RAPORT.xlsx`).

## Podpowiedź

- Wynik części A: buk G = 0,373 m², V = 5,349 m³; świerk G = 0,274 m², V = 2,980 m³.
- Pamiętaj o zamianie cm na m: `(df.d13_cm / 100) ** 2`.
- Folder `wyniki_kursu` musi istnieć przed zapisem: `Path("wyniki_kursu").mkdir(exist_ok=True)`.
- Błąd `PermissionError` przy zapisie `.xlsx` – plik jest otwarty w Excelu. Zamknij go.

## Podsumowanie

- `DataFrame` = tabela z nazwanymi kolumnami; nowa kolumna liczy się dla wszystkich wierszy,
- `.map(słownik)` – tabela przeliczeniowa (gatunek → f),
- `groupby(...).agg(...)` / `.sum()` – zestawienia; `for nr, grupa in df.groupby(...)` – pętla po grupach,
- V = g · h · f, g = π/4 · d²,
- `to_excel(...)` i `to_csv(sep=";", decimal=",")` – wynik dla Excela.
