"""
LEKCJA 7 - ROZWIĄZANIE: sąsiedzi punktu (KDTree) i usuwanie szumu
================================================================

Uruchomienie:
    python rozwiazanie_07_sasiedzi.py <plik.laz>
    python rozwiazanie_07_sasiedzi.py <plik.laz> 0.10 5
        (promień szukania w m, minimalna liczba sąsiadów)

Zapisuje do wyniki_kursu:
    <skan>_sasiedzi.laz  - chmura (przerzedzona do 3 cm) z nowym polem
                           "sasiedzi" i "szum" (1 = szum). W CloudCompare
                           pokoloruj po polu "sasiedzi" albo "szum".
"""

import sys
import time

import numpy as np
import laspy
from scipy.spatial import cKDTree

import kurs_wspolne as KW

sciezka = KW.sciezka_z_argumentu("python rozwiazanie_07_sasiedzi.py plik.laz [promien] [min_sasiadow]")
promien = float(sys.argv[2]) if len(sys.argv) > 2 else 0.10
min_sasiadow = int(sys.argv[3]) if len(sys.argv) > 3 else 5

chm = KW.wczytaj_chmure(sciezka)
xyz = chm["xyz"]

# ---- 1. przerzedzenie do 3 cm (lekcja 5) - żeby liczyło się szybko --------
kl = np.floor((xyz - xyz.min(axis=0)) / 0.03).astype(np.int64)
klucz = (kl[:, 0] << 42) | (kl[:, 1] << 21) | kl[:, 2]
_, pierwszy = np.unique(klucz, return_index=True)
del kl, klucz
pkt = xyz[np.sort(pierwszy)]
print(f"Po przerzedzeniu do 3 cm: {len(pkt):,} punktów".replace(",", " "))

# ---- 2. budowa drzewa KD ("spis z mapą") --------------------------------
t0 = time.time()
kd = cKDTree(pkt)
print(f"Drzewo KD zbudowane w {time.time() - t0:.1f} s")

# ---- 3. jedno pytanie: co jest w promieniu 1 m od środka chmury? -----------
srodek = np.median(pkt, axis=0)
blisko = kd.query_ball_point(srodek, r=1.0)        # lista numerów punktów
print(f"\nW promieniu 1 m od środka chmury ({srodek[0]:.1f}, {srodek[1]:.1f}, "
      f"{srodek[2]:.1f}) jest {len(blisko)} punktów")

odl, nr = kd.query(srodek, k=3)                    # 3 najbliższe punkty
print("Trzy najbliższe punkty są w odległości:", np.round(odl * 100, 1), "cm")

# ---- 4. dla KAŻDEGO punktu: ilu ma sąsiadów w promieniu ------------------
t0 = time.time()
ile = kd.query_ball_point(pkt, r=promien, return_length=True, workers=-1)
ile = ile - 1                                      # bez samego siebie
print(f"\nSąsiedzi w promieniu {promien * 100:g} cm policzeni w "
      f"{time.time() - t0:.1f} s")
print(f"  mediana: {np.median(ile):.0f} sąsiadów, najwięcej: {ile.max()}")

szum = ile < min_sasiadow
print(f"  szum (mniej niż {min_sasiadow} sąsiadów): {szum.sum():,} punktów "
      f"= {szum.mean() * 100:.2f}%".replace(",", " "))

# ---- 5. to samo inaczej: filtr SOR z tree_segmenter_tool ----------------
t0 = time.time()
srednia_odl = np.empty(len(pkt), dtype=np.float32)
PARTIA = 1_000_000                                 # partiami - mniej pamięci
for a in range(0, len(pkt), PARTIA):
    b = min(a + PARTIA, len(pkt))
    d, _ = kd.query(pkt[a:b], k=9, workers=-1)     # 8 sąsiadów + on sam
    srednia_odl[a:b] = d[:, 1:].mean(axis=1)
prog = srednia_odl.mean() + 2.0 * srednia_odl.std()
szum_sor = srednia_odl > prog
print(f"\nSOR (8 sąsiadów, próg średnia + 2 sigma = {prog * 100:.1f} cm): "
      f"{szum_sor.sum()} punktów szumu [{time.time() - t0:.1f} s]")
print(f"Obie metody zgodne co do {np.mean(szum == szum_sor) * 100:.1f}% punktów")

# czy szum to raczej czubki drzew? (pułapka opisana w tree_segmenter_tool)
h_pkt = KW.wysokosc_nad_gruntem(pkt)
print(f"Średnia wysokość szumu: {h_pkt[szum].mean() if szum.any() else 0:.1f} m, "
      f"wszystkich punktów: {h_pkt.mean():.1f} m")

# ---- 6. zapis z nowymi polami --------------------------------------------
nag = laspy.LasHeader(point_format=3, version="1.2")
nag.offsets = np.floor(pkt.min(axis=0))
nag.scales = np.array([0.001, 0.001, 0.001])
nag.add_extra_dim(laspy.ExtraBytesParams(name="sasiedzi", type=np.uint16))
nag.add_extra_dim(laspy.ExtraBytesParams(name="szum", type=np.uint8))
las = laspy.LasData(nag)
las.x, las.y, las.z = pkt[:, 0], pkt[:, 1], pkt[:, 2]
las.sasiedzi = np.minimum(ile, 65535).astype(np.uint16)
las.szum = szum.astype(np.uint8)
plik_wy = KW.folder_wynikow() / f"{chm['nazwa']}_sasiedzi.laz"
las.write(str(plik_wy))
print(f"\nZapisano: {plik_wy}")
