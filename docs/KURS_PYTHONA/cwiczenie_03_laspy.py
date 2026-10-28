"""
LEKCJA 3 - ĆWICZENIE: czytamy plik .las / .laz
==============================================

Uruchomienie:
    python cwiczenie_03_laspy.py <plik.laz>
"""

import sys
from pathlib import Path

import numpy as np
import laspy

# TODO 1: jeśli nie podano pliku (len(sys.argv) < 2), zakończ program
#         z komunikatem:  sys.exit("BŁĄD: podaj plik .laz ...")
if len(sys.argv) < 2:
    print("   [TODO 1] tu powinien być sys.exit(...) z jasnym komunikatem")
    sys.exit(1)
sciezka = Path(sys.argv[1])

# TODO 2: otwórz sam nagłówek i wypisz liczbę punktów i zasięg
with laspy.open(str(sciezka)) as plik:
    nag = plik.header
    print("Liczba punktów:", nag.point_count)
    print("   [TODO 2] wypisz też nag.mins i nag.maxs")

las = laspy.read(str(sciezka))
pola = list(las.point_format.dimension_names)
print("Pola:", pola)

# TODO 3: wytnij x, y, z jako tablice numpy: np.asarray(las.x) itd.
#         i wypisz pierwszy punkt
print("   [TODO 3] x = np.asarray(las.x) ...")

# TODO 4: jeśli w polach jest "treeID" albo "treeID_pred", policz drzewa:
#         drzewo = np.asarray(las["treeID"])
#         numery = np.unique(drzewo[drzewo > 0]);  len(numery)
if "treeID" in pola or "treeID_pred" in pola:
    print("   [TODO 4] policz drzewa (np.unique)")
else:
    print("Brak numerów drzew - surowy skan.")

# TODO 5: jeśli jest pole "czesc", policz punkty każdej części:
#         np.bincount(np.asarray(las["czesc"]), minlength=5)
#         (0 nic, 1 pień, 2 gałęzie, 3 liście, 4 podszyt)
if "czesc" in pola:
    print("   [TODO 5] policz punkty pnia, gałęzi, liści")
