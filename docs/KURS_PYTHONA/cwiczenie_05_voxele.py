"""
LEKCJA 5 - ĆWICZENIE: przerzedzanie chmury voxelami
===================================================

Uruchomienie:
    python cwiczenie_05_voxele.py <plik.laz>
"""

import sys
from pathlib import Path

import numpy as np
import laspy

if len(sys.argv) < 2:
    sys.exit("BŁĄD: podaj plik .las/.laz:  python cwiczenie_05_voxele.py plik.laz")
sciezka = Path(sys.argv[1])
las = laspy.read(str(sciezka))
punkty = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                          np.asarray(las.z)])
print("Punktów:", len(punkty))

voxel = 0.05   # 5 cm

# TODO 1: policz numery voxeli każdego punktu:
#         kl = np.floor((punkty - punkty.min(axis=0)) / voxel).astype(np.int64)
kl = None
print("   [TODO 1] policz kl")

# TODO 2: spakuj trzy numery w jedną liczbę:
#         klucz = (kl[:, 0] << 42) | (kl[:, 1] << 21) | kl[:, 2]
# TODO 3: znajdź pierwszy punkt każdego voxela:
#         _, pierwszy = np.unique(klucz, return_index=True)
#         i wypisz, ile voxeli wyszło i jaki to procent punktów
if kl is None:
    print("   [TODO 2-3] najpierw TODO 1")

# TODO 4: powtórz dla voxela 1 cm, 2,5 cm i 10 cm (pętla for).
#         Jak zmienia się liczba punktów?

# TODO 5: zapisz przerzedzoną chmurę:
#         nowy = laspy.LasData(las.header)
#         nowy.points = las.points[np.sort(pierwszy)]
#         nowy.write("wyniki_kursu/przerzedzona.laz")
