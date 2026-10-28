"""
LEKCJA 4 - ROZWIĄZANIE: wysokość nad gruntem i plaster na 1,3 m
===============================================================

Uruchomienie:
    python rozwiazanie_04_wysokosc.py <plik.laz>

Zapisuje do folderu wyniki_kursu:
    <skan>_plaster_1_3m.laz   - same punkty z plastra 1,3 m ± 5 cm
                                (otwórz w CloudCompare - zobaczysz "kółka" pni)
"""

import sys
from pathlib import Path

import numpy as np
import laspy


def model_terenu(x, y, z, komorka=1.0):
    """Najniższy punkt w każdej komórce siatki = grunt.
    Zwraca z gruntu POD każdym punktem."""
    kol = ((x - x.min()) / komorka).astype(np.int64)   # numer kolumny siatki
    wie = ((y - y.min()) / komorka).astype(np.int64)   # numer wiersza siatki
    siatka = np.full((wie.max() + 1, kol.max() + 1), np.inf)
    np.minimum.at(siatka, (wie, kol), z)               # minimum w komórce
    return siatka[wie, kol]                            # grunt pod punktem


# ---- 1. wczytanie --------------------------------------------------------
if len(sys.argv) < 2:
    sys.exit("BŁĄD: podaj plik .las/.laz, np.\n"
             "      python rozwiazanie_04_wysokosc.py skan_segmenty.laz")
sciezka = Path(sys.argv[1])
if not sciezka.exists():
    sys.exit(f"BŁĄD: nie ma pliku {sciezka}")

las = laspy.read(str(sciezka))
pola = set(las.point_format.dimension_names)
x, y, z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)
print(f"Punktów: {len(x):,}".replace(",", " "))

# ---- 2. wysokość nad gruntem: nasza, prosta ------------------------------
grunt = model_terenu(x, y, z, komorka=1.0)
h_nasza = z - grunt
print(f"Teren (najniższe punkty w komórkach 1 m): od {grunt.min():.2f} "
      f"do {grunt.max():.2f} m  (deniwelacja {grunt.max() - grunt.min():.2f} m)")

# ---- 3. ... albo dokładniejsza z programu LidarTreeSegmenter, jeśli jest w pliku ---------------
if "wys_nad_grunt" in pola:
    h = np.asarray(las["wys_nad_grunt"], dtype=np.float64)
    roznica = h_nasza - h
    print("W pliku jest pole wys_nad_grunt (z programu LidarTreeSegmenter) - używam go.")
    print(f"Porównanie: nasza prosta metoda różni się od wyniku LidarTreeSegmenter średnio o "
          f"{np.median(np.abs(roznica)) * 100:.1f} cm (mediana)")
else:
    h = h_nasza
    print("Brak pola wys_nad_grunt - używam naszej prostej wysokości.")

# ---- 4. filtry wysokości (maski) -----------------------------------------
grunt_maska = h < 0.10                    # punkty gruntu (do 10 cm)
nisko = (h >= 0.10) & (h < 2.0)           # runo, podszyt, nabiegi
plaster = np.abs(h - 1.3) <= 0.05         # pierśnica: 1,25 - 1,35 m
korona = h >= 2.0

print(f"\nGrunt (h < 10 cm):        {grunt_maska.sum():>10}")
print(f"Nisko (10 cm - 2 m):      {nisko.sum():>10}")
print(f"Plaster 1,3 m ± 5 cm:     {plaster.sum():>10}")
print(f"Wyżej niż 2 m:            {korona.sum():>10}")

# ---- 5. punkty plastra na drzewo -----------------------------------------
pole_drzewa = next((p for p in ("treeID", "treeID_pred") if p in pola), None)
if pole_drzewa:
    drzewo = np.asarray(las[pole_drzewa])
    w_plastrze = drzewo[plaster & (drzewo > 0)]
    numery, ile = np.unique(w_plastrze, return_counts=True)
    kolej = np.argsort(ile)[::-1]               # od największej liczby
    print(f"\nPięć drzew z największą liczbą punktów w plastrze 1,3 m:")
    for i in kolej[:5]:
        print(f"  drzewo {numery[i]:4d}: {ile[i]:6d} punktów")

    # wysokość każdego drzewa = najwyższy punkt (99,9 percentyl, bez szumu)
    print("\nWysokości pierwszych 5 drzew (99,9 percentyl h):")
    for t in numery[:5]:
        print(f"  drzewo {t:4d}: {np.percentile(h[drzewo == t], 99.9):5.1f} m")

# ---- 6. zapis plastra jako nowy .laz -------------------------------------
wyniki = Path("wyniki_kursu")
wyniki.mkdir(exist_ok=True)
plik_wy = wyniki / f"{sciezka.stem}_plaster_1_3m.laz"
nowy = laspy.LasData(las.header)        # ten sam nagłówek (te same pola)
nowy.points = las.points[plaster]       # tylko punkty z plastra
nowy.write(str(plik_wy))
print(f"\nZapisano plaster: {plik_wy}  ({plaster.sum()} pkt)")
