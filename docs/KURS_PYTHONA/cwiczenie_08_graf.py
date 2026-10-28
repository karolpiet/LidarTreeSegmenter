"""
LEKCJA 8 - ĆWICZENIE: graf i algorytm Dijkstry
==============================================

Uruchomienie:
    python cwiczenie_08_graf.py <plik.laz> [nr_drzewa]

Najpierw rozgrzewka na małym grafie "na papierze", potem prawdziwe drzewo.
"""

import sys

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

import kurs_wspolne as KW

# ---- ROZGRZEWKA: 5 punktów, jak 5 drzew połączonych ścieżkami -----------
#  0 --1.0-- 1 --1.0-- 2
#  |                   |
# 4.0                 1.0
#  |                   |
#  3 -------1.0------- 4
zrodlo = np.array([0, 1, 0, 2, 3])
cel = np.array([1, 2, 3, 4, 4])
waga = np.array([1.0, 1.0, 4.0, 1.0, 1.0])
graf = coo_matrix((waga, (zrodlo, cel)), shape=(5, 5)).tocsr()

# TODO 1: policz najkrótsze drogi z punktu 0 do wszystkich:
#         droga = dijkstra(graf, directed=False, indices=0)
#         Ile wynosi droga do punktu 3? (prosto 4.0, a naokoło?)
print("   [TODO 1] policz dijkstra(graf, directed=False, indices=0)")

# ---- PRAWDZIWE DRZEWO ----------------------------------------------------
sciezka = KW.sciezka_z_argumentu("python cwiczenie_08_graf.py plik.laz [nr_drzewa]")
chm = KW.wczytaj_chmure(sciezka)
nr = int(sys.argv[2]) if len(sys.argv) > 2 else None
nr, idx = KW.wybierz_drzewo(chm, nr)
pkt = chm["xyz"][idx]

# voxele 5 cm (gotowe)
kl = np.floor((pkt - pkt.min(axis=0)) / 0.05).astype(np.int64)
klucz = (kl[:, 0] << 42) | (kl[:, 1] << 21) | kl[:, 2]
_, pierwszy = np.unique(klucz, return_index=True)
vox = pkt[pierwszy]
print("Voxeli:", len(vox))

# TODO 2: zbuduj drzewo KD i znajdź 10 sąsiadów każdego voxela:
#         from scipy.spatial import cKDTree
#         odl, sas = cKDTree(vox).query(vox, k=11)
# TODO 3: zrób z tego graf (jak w rozgrzewce): zrodlo, cel, waga
#         - pomiń kolumnę 0 (voxel sam ze sobą) i krawędzie dłuższe niż 0,15 m
# TODO 4: start = voxele najniższe (vox[:, 2] < vox[:, 2].min() + 0.3)
#         droga = dijkstra(graf, directed=False, indices=start, min_only=True)
# TODO 5: wypisz drogę do najwyższego voxela i porównaj z jego wysokością
print("   [TODO 2-5] zbuduj graf drzewa i policz Dijkstrę")
