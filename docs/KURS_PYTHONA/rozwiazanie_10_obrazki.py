"""
LEKCJA 10 - ROZWIĄZANIE: obrazki w matplotlib
=============================================

Uruchomienie:
    python rozwiazanie_10_obrazki.py <plik.laz>              (drzewo wybrane samo)
    python rozwiazanie_10_obrazki.py <plik.laz> <nr_drzewa>

Zapisuje do wyniki_kursu:
    <skan>_mapa.png                - cały skan z góry, numery drzew
    <skan>_drzewo_<nr>_karta.png   - jedno drzewo: z góry i z boku
"""

import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

import kurs_wspolne as KW

# kolory części (jak na obrazkach LidarTreeSegmenter): nic, pień, gałęzie, liście, podszyt
KOLORY = np.array([[.70, .70, .70], [.45, .22, .05], [.85, .55, .20],
                   [.20, .60, .20], [.62, .66, .78]])

sciezka = KW.sciezka_z_argumentu("python rozwiazanie_10_obrazki.py plik.laz [nr_drzewa]")
chm = KW.wczytaj_chmure(sciezka)
xyz, h, drzewo, czesc = chm["xyz"], chm["h"], chm["drzewo"], chm["czesc"]
rng = np.random.default_rng(0)
wyniki = KW.folder_wynikow()

# ---- 1. MAPA całego skanu z góry -----------------------------------------
# 15 mln punktów to za dużo do rysowania - losujemy 300 tysięcy
ile = min(300_000, len(xyz))
los = rng.choice(len(xyz), ile, replace=False)
los = los[np.argsort(h[los])]                     # wyższe punkty rysujemy na wierzchu

fig, ax = plt.subplots(figsize=(9, 9))
if drzewo is not None:
    # każde drzewo innym kolorem (20 kolorów po kolei), punkty bez drzewa szare
    paleta = ListedColormap(plt.cm.tab20(np.arange(20)))
    bez = drzewo[los] <= 0
    ax.scatter(xyz[los[bez], 0], xyz[los[bez], 1], s=0.2, c="#cccccc")
    ax.scatter(xyz[los[~bez], 0], xyz[los[~bez], 1], s=0.2,
               c=drzewo[los[~bez]] % 20, cmap=paleta, vmin=0, vmax=19)
    # numer drzewa w miejscu jego pnia (mediana punktów na 1-2 m)
    for nr in np.unique(drzewo[drzewo > 0]):
        m = (drzewo == nr) & (h > 1) & (h < 2)
        if m.sum() > 20:
            ax.text(np.median(xyz[m, 0]), np.median(xyz[m, 1]), str(nr),
                    fontsize=8, ha="center", va="center",
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", alpha=0.8, lw=0))
    ax.set_title(f"{chm['nazwa']} - widok z góry, kolor = drzewo")
else:
    sc = ax.scatter(xyz[los, 0], xyz[los, 1], s=0.2, c=h[los], cmap="viridis")
    fig.colorbar(sc, ax=ax, label="wysokość nad gruntem [m]", shrink=0.7)
    ax.set_title(f"{chm['nazwa']} - widok z góry, kolor = wysokość")
ax.set_aspect("equal")
ax.set_xlabel("X [m]")
ax.set_ylabel("Y [m]")
png_mapa = wyniki / f"{chm['nazwa']}_mapa.png"
fig.savefig(png_mapa, dpi=120, bbox_inches="tight")
print(f"Zapisano mapę: {png_mapa}")

# ---- 2. KARTA jednego drzewa ----------------------------------------------
nr = int(sys.argv[2]) if len(sys.argv) > 2 else None
nr, idx = KW.wybierz_drzewo(chm, nr)
if len(idx) > 150_000:                            # do rysowania wystarczy próbka
    idx = rng.choice(idx, 150_000, replace=False)
p, hh = xyz[idx], h[idx]
if czesc is not None:
    kolor = KOLORY[czesc[idx]]
    idx_kol = np.argsort(czesc[idx] == 1, kind="stable")   # pień na wierzchu
    p, hh, kolor = p[idx_kol], hh[idx_kol], kolor[idx_kol]
    opis = "brąz: pień, pomarańczowy: gałęzie, zielony: liście, szary: podszyt"
else:
    kolor = plt.cm.viridis(np.clip(hh / max(hh.max(), 1), 0, 1))
    opis = "kolor = wysokość nad gruntem"
cx, cy = np.median(p[:, 0]), np.median(p[:, 1])

fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 7),
                                    gridspec_kw={"width_ratios": [1, 1, 1.2]})
# a) z boku: wschód - zachód
ax1.scatter(p[:, 0] - cx, hh, s=0.3, c=kolor, linewidths=0)
ax1.set_xlabel("wschód - zachód [m]")
ax1.set_ylabel("wysokość nad gruntem [m]")
# b) z boku: północ - południe
ax2.scatter(p[:, 1] - cy, hh, s=0.3, c=kolor, linewidths=0)
ax2.set_xlabel("południe - północ [m]")
for ax in (ax1, ax2):
    ax.axhline(1.3, color="red", lw=1, ls="--")   # linia pierśnicy
    ax.set_aspect("equal")
    ax.grid(color="#e5e5e5")
# c) z góry
ax3.scatter(p[:, 0] - cx, p[:, 1] - cy, s=0.3, c=kolor, linewidths=0)
ax3.set_aspect("equal")
ax3.set_xlabel("X [m]")
ax3.set_ylabel("Y [m]")
ax3.set_title("z góry (rzut korony)")
ax3.grid(color="#e5e5e5")
wys = np.percentile(hh, 99.9)
fig.suptitle(f"Drzewo {nr} - wysokość {wys:.1f} m\n{opis}", fontsize=12)
png_karta = wyniki / f"{chm['nazwa']}_drzewo_{nr}_karta.png"
fig.savefig(png_karta, dpi=110, bbox_inches="tight")
print(f"Zapisano kartę drzewa: {png_karta}")

plt.show()       # na Windows otworzą się dwa okna; zamknij je, by zakończyć
