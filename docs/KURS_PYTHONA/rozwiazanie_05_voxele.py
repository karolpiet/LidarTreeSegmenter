"""
LEKCJA 5 - ROZWIĄZANIE: przerzedzanie chmury voxelami
=====================================================

Uruchomienie:
    python rozwiazanie_05_voxele.py <plik.laz>
    python rozwiazanie_05_voxele.py <plik.laz> 0.05     (własny voxel w m)

Zapisuje do wyniki_kursu:
    <skan>_voxel_5cm.laz   - chmura przerzedzona (1 punkt na voxel)
"""

import sys
import time
from pathlib import Path

import numpy as np
import laspy


def numery_voxeli(punkty, voxel):
    """Dla każdego punktu: w którym sześcianiku (voxelu) leży.
    Trzy numery (kolumna, wiersz, piętro) pakujemy w JEDNĄ liczbę -
    tak samo jak w programie LidarTreeSegmenter (oszczędza dużo pamięci)."""
    kl = np.floor((punkty - punkty.min(axis=0)) / voxel).astype(np.int64)
    return (kl[:, 0] << 42) | (kl[:, 1] << 21) | kl[:, 2]


# ---- 1. wczytanie --------------------------------------------------------
if len(sys.argv) < 2:
    sys.exit("BŁĄD: podaj plik .las/.laz:\n"
             "      python rozwiazanie_05_voxele.py plik.laz [voxel_w_m]")
sciezka = Path(sys.argv[1])
if not sciezka.exists():
    sys.exit(f"BŁĄD: nie ma pliku {sciezka}")
voxel_glowny = float(sys.argv[2]) if len(sys.argv) > 2 else 0.05

las = laspy.read(str(sciezka))
punkty = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                          np.asarray(las.z)])
n = len(punkty)
print(f"Punktów w pliku: {n:,}".replace(",", " "))

# ---- 2. mały przykład "na palcach" --------------------------------------
print("\nPrzykład na 5 punktach, voxel 10 cm:")
maly = np.array([[0.01, 0.02, 0.03],
                 [0.04, 0.08, 0.01],     # ten sam voxel co pierwszy
                 [0.15, 0.02, 0.03],     # voxel obok w osi X
                 [0.16, 0.05, 0.09],     # ten sam co trzeci
                 [0.55, 0.55, 1.30]])    # daleko
kl = np.floor(maly / 0.10).astype(int)
print("numery voxeli (kolumna, wiersz, piętro):\n", kl)
unikalne, pierwszy, ile = np.unique(kl, axis=0, return_index=True,
                                    return_counts=True)
print("różnych voxeli:", len(unikalne), " punktów w każdym:", ile)
print("indeksy punktów, które zostają:", np.sort(pierwszy))

# ---- 3. różne wielkości voxela ------------------------------------------
print("\nIle zostaje punktów przy różnych voxelach:")
for v in (0.01, 0.025, 0.05, 0.10):
    t0 = time.time()
    klucz = numery_voxeli(punkty, v)
    nv = len(np.unique(klucz))
    print(f"  voxel {v * 100:4.1f} cm: {nv:>11,} punktów  "
          f"({nv / n * 100:5.1f}%)   [{time.time() - t0:.1f} s]".replace(",", " "))
    del klucz

# ---- 4. właściwe przerzedzenie ------------------------------------------
klucz = numery_voxeli(punkty, voxel_glowny)
_, pierwszy, odwr = np.unique(klucz, return_index=True, return_inverse=True)
odwr = odwr.ravel()
nv = len(pierwszy)

# a) pierwszy punkt z każdego voxela (zachowuje wszystkie pola punktu)
zostaw = np.sort(pierwszy)

# b) środek ciężkości każdego voxela (jak w programie LidarTreeSegmenter, krok 3)
licz = np.bincount(odwr, minlength=nv).astype(float)
srodki = np.column_stack([np.bincount(odwr, weights=punkty[:, i],
                                      minlength=nv) / licz for i in range(3)])
print(f"\nVoxel {voxel_glowny * 100:g} cm: {nv:,} voxeli".replace(",", " "))
print(f"Najgęstszy voxel ma {int(licz.max())} punktów, "
      f"średnio {licz.mean():.1f} punktu na voxel")
print("Środek pierwszego voxela:", np.round(srodki[0], 3))

# ---- 5. zapis ------------------------------------------------------------
wyniki = Path("wyniki_kursu")
wyniki.mkdir(exist_ok=True)
plik_wy = wyniki / f"{sciezka.stem}_voxel_{voxel_glowny * 100:g}cm.laz"
nowy = laspy.LasData(las.header)
nowy.points = las.points[zostaw]
nowy.write(str(plik_wy))
print(f"Zapisano: {plik_wy}")
