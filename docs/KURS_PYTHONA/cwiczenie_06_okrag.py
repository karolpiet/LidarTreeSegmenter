"""
LEKCJA 6 - ĆWICZENIE: pierśnica z okręgu (metoda Kåsy)
======================================================

Uruchomienie:
    python cwiczenie_06_okrag.py <plik.laz> [nr_drzewa]
"""

import sys

import numpy as np

import kurs_wspolne as KW


def okrag_kasa(x, y):
    """Zwraca (cx, cy, r)."""
    # TODO 1: zbuduj macierz A = [x, y, 1]:  np.column_stack([x, y, np.ones_like(x)])
    # TODO 2: zbuduj wektor b = x² + y²
    # TODO 3: rozwiąż:  c, *_ = np.linalg.lstsq(A, b, rcond=None)
    # TODO 4: cx = c[0] / 2,  cy = c[1] / 2,  r = sqrt(c[2] + cx² + cy²)
    print("   [TODO 1-4] uzupełnij funkcję okrag_kasa()")
    return float(np.mean(x)), float(np.mean(y)), 0.0


# Test na sztucznym okręgu: r = 0,20 m. Po uzupełnieniu ma wyjść 20 cm.
kat = np.linspace(0, np.pi, 50)
cx, cy, r = okrag_kasa(5 + 0.2 * np.cos(kat), 7 + 0.2 * np.sin(kat))
print(f"Test: r = {r * 100:.1f} cm (powinno być 20.0)")

sciezka = KW.sciezka_z_argumentu("python cwiczenie_06_okrag.py plik.laz [nr_drzewa]")
chm = KW.wczytaj_chmure(sciezka)
nr = int(sys.argv[2]) if len(sys.argv) > 2 else None
nr, idx = KW.wybierz_drzewo(chm, nr)
xyz, h = chm["xyz"][idx], chm["h"][idx]

# TODO 5: wybierz punkty plastra 1,3 m ± 5 cm:  pl = xyz[np.abs(h - 1.3) <= 0.05]
pl = xyz[:0]
print("Punktów w plastrze:", len(pl), "  [TODO 5]")

# TODO 6: dopasuj okrąg do pl[:, 0], pl[:, 1] i wypisz pierśnicę = 2 · r w cm
if len(pl) >= 3:
    cx, cy, r = okrag_kasa(pl[:, 0], pl[:, 1])
    print(f"Pierśnica drzewa {nr}: {2 * r * 100:.1f} cm")
else:
    print("   [TODO 6] po TODO 5 policz pierśnicę")
