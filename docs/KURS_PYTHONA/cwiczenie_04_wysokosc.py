"""
LEKCJA 4 - ĆWICZENIE: wysokość nad gruntem i plaster na 1,3 m
=============================================================

Uruchomienie:
    python cwiczenie_04_wysokosc.py <plik.laz>
"""

import sys
from pathlib import Path

import numpy as np
import laspy


def model_terenu(x, y, z, komorka=1.0):
    kol = ((x - x.min()) / komorka).astype(np.int64)
    wie = ((y - y.min()) / komorka).astype(np.int64)
    siatka = np.full((wie.max() + 1, kol.max() + 1), np.inf)
    np.minimum.at(siatka, (wie, kol), z)
    return siatka[wie, kol]


if len(sys.argv) < 2:
    sys.exit("BŁĄD: podaj plik .las/.laz:  python cwiczenie_04_wysokosc.py plik.laz")
sciezka = Path(sys.argv[1])
las = laspy.read(str(sciezka))
pola = set(las.point_format.dimension_names)
x, y, z = np.asarray(las.x), np.asarray(las.y), np.asarray(las.z)

# TODO 1: policz wysokość nad gruntem: h = z - model_terenu(x, y, z)
h = z - z.min()      # <- to tylko "od najniższego punktu"; popraw na model terenu
print("   [TODO 1] użyj model_terenu()")

# TODO 2: jeśli w pliku jest pole "wys_nad_grunt", użyj go zamiast h:
#         h = np.asarray(las["wys_nad_grunt"], dtype=np.float64)
if "wys_nad_grunt" in pola:
    print("   [TODO 2] w pliku jest wys_nad_grunt - użyj go")

# TODO 3: zrób maskę plastra 1,3 m ± 5 cm:  np.abs(h - 1.3) <= 0.05
plaster = np.zeros(len(h), dtype=bool)     # <- popraw
print("Punktów w plastrze:", plaster.sum())

# TODO 4: maska gruntu (h < 0.10) i maska korony (h >= 2.0) - wypisz liczby
print("   [TODO 4] policz punkty gruntu i korony")

# TODO 5: zapisz plaster do nowego pliku:
#         nowy = laspy.LasData(las.header); nowy.points = las.points[plaster]
#         nowy.write("wyniki_kursu/plaster.laz")   (najpierw utwórz folder)
if plaster.sum() == 0:
    print("   [TODO 5] plaster pusty - najpierw uzupełnij TODO 3")
