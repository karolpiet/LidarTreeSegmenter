"""
LEKCJA 10 - ĆWICZENIE: obrazki w matplotlib
===========================================

Uruchomienie:
    python cwiczenie_10_obrazki.py <plik.laz> [nr_drzewa]
"""

import sys

import numpy as np
import matplotlib.pyplot as plt

import kurs_wspolne as KW

sciezka = KW.sciezka_z_argumentu("python cwiczenie_10_obrazki.py plik.laz [nr_drzewa]")
chm = KW.wczytaj_chmure(sciezka)
nr = int(sys.argv[2]) if len(sys.argv) > 2 else None
nr, idx = KW.wybierz_drzewo(chm, nr)

# próbka do rysowania (gotowe)
rng = np.random.default_rng(0)
if len(idx) > 100_000:
    idx = rng.choice(idx, 100_000, replace=False)
p, h = chm["xyz"][idx], chm["h"][idx]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 7))

# TODO 1: na ax1 narysuj widok z boku: ax1.scatter(p[:, 0], h, s=0.3, c=h)
# TODO 2: dodaj czerwoną przerywaną linię na 1,3 m: ax1.axhline(1.3, color="red", ls="--")
# TODO 3: na ax2 narysuj widok z góry: ax2.scatter(p[:, 0], p[:, 1], s=0.3, c=h)
# TODO 4: ustaw równe skale osi (ax.set_aspect("equal")) i podpisy osi
#         (ax.set_xlabel("X [m]"), ax.set_ylabel(...))
ax1.set_title("[TODO 1-2] widok z boku")
ax2.set_title("[TODO 3] widok z góry")
fig.suptitle(f"Drzewo {nr}")

# TODO 5: zapisz obrazek do pliku PRZED plt.show():
#         fig.savefig(KW.folder_wynikow() / f"drzewo_{nr}.png", dpi=110)
print("   [TODO 5] zapisz PNG")
plt.show()
