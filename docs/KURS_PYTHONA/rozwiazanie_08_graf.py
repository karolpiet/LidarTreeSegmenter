"""
LEKCJA 8 - ROZWIĄZANIE: graf i algorytm Dijkstry - droga "po drewnie"
====================================================================

Uruchomienie:
    python rozwiazanie_08_graf.py <plik.laz>              (drzewo wybrane samo)
    python rozwiazanie_08_graf.py <plik.laz> <nr_drzewa>

Co robi:
  1. bierze punkty jednego drzewa i przerzedza je do voxeli 5 cm,
  2. łączy każdy voxel z najbliższymi sąsiadami (to jest GRAF),
  3. algorytmem Dijkstry liczy, jak daleko jest od podstawy pnia do każdego
     voxela, idąc TYLKO po punktach (jak wiewiórka po drewnie),
  4. odtwarza drogę od wierzchołka drzewa w dół, do ziemi.

Zapisuje do wyniki_kursu:  <skan>_drzewo_<nr>_dijkstra.png
"""

import sys

import numpy as np
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra

import kurs_wspolne as KW

VOXEL = 0.05          # 5 cm
SASIEDZI = 10         # z iloma najbliższymi voxelami łączymy każdy voxel
MAX_KRAWEDZ = 0.15    # dłuższych połączeń nie robimy (przez "powietrze")

sciezka = KW.sciezka_z_argumentu("python rozwiazanie_08_graf.py plik.laz [nr_drzewa]")
chm = KW.wczytaj_chmure(sciezka)
nr = int(sys.argv[2]) if len(sys.argv) > 2 else None
nr, idx = KW.wybierz_drzewo(chm, nr)
if chm["czesc"] is not None:
    # bez podszytu (4) i "niczego" (0): krzewy przy ziemi dałyby fałszywe starty
    idx = idx[np.isin(chm["czesc"][idx], [1, 2, 3])]
pkt, h = chm["xyz"][idx], chm["h"][idx]
print(f"Drzewo {nr}: {len(pkt):,} punktów".replace(",", " "))

# ---- 1. voxele (lekcja 5) -------------------------------------------------
kl = np.floor((pkt - pkt.min(axis=0)) / VOXEL).astype(np.int64)
klucz = (kl[:, 0] << 42) | (kl[:, 1] << 21) | kl[:, 2]
_, pierwszy, odwr = np.unique(klucz, return_index=True, return_inverse=True)
odwr = odwr.ravel()
nv = len(pierwszy)
licz = np.bincount(odwr, minlength=nv).astype(float)
srodki = np.column_stack([np.bincount(odwr, weights=pkt[:, i], minlength=nv) / licz
                          for i in range(3)])
h_vox = np.bincount(odwr, weights=h, minlength=nv) / licz
print(f"Voxeli 5 cm: {nv:,}".replace(",", " "))

# ---- 2. graf: każdy voxel łączymy z sąsiadami (lekcja 7) -----------------
kd = cKDTree(srodki)
odl, sas = kd.query(srodki, k=min(SASIEDZI + 1, nv), workers=-1)
odl, sas = odl[:, 1:], sas[:, 1:]                   # bez samego siebie
zrodlo = np.repeat(np.arange(nv), odl.shape[1])      # skąd
cel = sas.ravel()                                    # dokąd
waga = odl.ravel()                                   # ile metrów
ok = waga <= MAX_KRAWEDZ
graf = coo_matrix((np.maximum(waga[ok], 0.001), (zrodlo[ok], cel[ok])),
                  shape=(nv, nv)).tocsr()
print(f"Krawędzi (połączeń) w grafie: {ok.sum():,}".replace(",", " "))

# ---- 3. start: najniższe voxele drzewa (podstawa pnia) -------------------
if chm["czesc"] is not None and (chm["czesc"][idx] == 1).any():
    # mamy oznaczony pień: start = najniższe voxele PNIA
    jest_pniem = chm["czesc"][idx][pierwszy] == 1
    dol = h_vox[jest_pniem].min()
    starty = np.flatnonzero(jest_pniem & (h_vox <= dol + 0.30))
else:
    dol = h_vox.min()
    starty = np.flatnonzero(h_vox <= dol + 0.30)
print(f"Voxeli startowych (najniższe 30 cm drzewa): {len(starty)}")

# ---- 4. Dijkstra ze wszystkich startów naraz ------------------------------
droga, poprzednik, skad = dijkstra(graf, directed=False, indices=starty,
                                   return_predecessors=True, min_only=True)
dojechal = np.isfinite(droga)
print(f"Dijkstra dotarła do {dojechal.mean() * 100:.1f}% voxeli "
      f"(reszta jest odcięta - dziura w skanie albo obcy fragment)")

# ---- 5. droga od wierzchołka w dół ---------------------------------------
szczyt = np.flatnonzero(dojechal)[np.argmax(h_vox[dojechal])]
trasa = [szczyt]
while poprzednik[trasa[-1]] >= 0:                    # -9999 = koniec (start)
    trasa.append(poprzednik[trasa[-1]])
trasa = np.array(trasa)
print(f"\nWierzchołek: {h_vox[szczyt]:.1f} m nad gruntem")
print(f"Droga po drewnie od podstawy do wierzchołka: {droga[szczyt]:.1f} m "
      f"({len(trasa)} voxeli)")
print(f"Stosunek drogi do wysokości: {droga[szczyt] / max(h_vox[szczyt] - dol, 0.1):.2f}"
      "  (blisko 1 = prosty pień)")

# wychylenie pnia: o ile środek trasy na górze odsunął się od dołu
d_poz = np.hypot(srodki[trasa[0], 0] - srodki[trasa[-1], 0],
                 srodki[trasa[0], 1] - srodki[trasa[-1], 1])
print(f"Wierzchołek jest przesunięty w poziomie o {d_poz:.2f} m od podstawy")

# ---- 6. obrazek z boku: kolor = droga po drewnie -------------------------
fig, ax = plt.subplots(figsize=(7, 9))
m = dojechal
ax.scatter(srodki[~m, 0], h_vox[~m], c="#bbbbbb", s=1, label="nieosiągalne")
sc = ax.scatter(srodki[m, 0], h_vox[m], c=droga[m], s=1, cmap="viridis")
ax.plot(srodki[trasa, 0], h_vox[trasa], "r-", lw=2, label="droga z wierzchołka")
fig.colorbar(sc, ax=ax, label="droga po drewnie od podstawy [m]")
ax.set_aspect("equal")
ax.set_xlabel("X [m]")
ax.set_ylabel("wysokość nad gruntem [m]")
ax.set_title(f"Drzewo {nr} - algorytm Dijkstry (widok z boku)")
ax.legend(loc="lower right", markerscale=8)
png = KW.folder_wynikow() / f"{chm['nazwa']}_drzewo_{nr}_dijkstra.png"
fig.savefig(png, dpi=110, bbox_inches="tight")
print(f"Zapisano obrazek: {png}")
plt.show()
