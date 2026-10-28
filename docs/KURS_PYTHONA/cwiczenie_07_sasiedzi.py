"""
LEKCJA 7 - ĆWICZENIE: sąsiedzi punktu (KDTree)
==============================================

Uruchomienie:
    python cwiczenie_07_sasiedzi.py <plik.laz>
"""

import numpy as np
from scipy.spatial import cKDTree

import kurs_wspolne as KW

sciezka = KW.sciezka_z_argumentu("python cwiczenie_07_sasiedzi.py plik.laz")
chm = KW.wczytaj_chmure(sciezka)
xyz = chm["xyz"]

# przerzedzenie do 3 cm (lekcja 5) - gotowe
kl = np.floor((xyz - xyz.min(axis=0)) / 0.03).astype(np.int64)
klucz = (kl[:, 0] << 42) | (kl[:, 1] << 21) | kl[:, 2]
_, pierwszy = np.unique(klucz, return_index=True)
pkt = xyz[np.sort(pierwszy)]
print("Punktów po przerzedzeniu:", len(pkt))

# TODO 1: zbuduj drzewo KD:  kd = cKDTree(pkt)
kd = None
print("   [TODO 1] kd = cKDTree(pkt)")

# TODO 2: ile punktów leży w promieniu 1 m od środka chmury?
#         srodek = np.median(pkt, axis=0)
#         blisko = kd.query_ball_point(srodek, r=1.0);  len(blisko)
if kd is not None:
    print("   [TODO 2] policz punkty w promieniu 1 m")

# TODO 3: dla każdego punktu policz sąsiadów w promieniu 10 cm:
#         ile = kd.query_ball_point(pkt, r=0.10, return_length=True, workers=-1) - 1
# TODO 4: szum = ile < 5 ; wypisz, ile to punktów i jaki procent
print("   [TODO 3-4] policz sąsiadów i szum")

# TODO 5 (dla chętnych): zmień promień na 5 cm i 20 cm. Co się dzieje
#         z liczbą punktów szumu? Dlaczego?
