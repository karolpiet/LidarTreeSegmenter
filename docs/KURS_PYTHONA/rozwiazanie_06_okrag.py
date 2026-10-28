"""
LEKCJA 6 - ROZWIĄZANIE: pierśnica z okręgu dopasowanego do plastra 1,3 m
=======================================================================

Uruchomienie:
    python rozwiazanie_06_okrag.py <plik.laz>              (drzewo wybrane samo)
    python rozwiazanie_06_okrag.py <plik.laz> <nr_drzewa>  (np. 17)

Zapisuje do wyniki_kursu:  <skan>_drzewo_<nr>_okrag.png
"""

import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

import kurs_wspolne as KW          # nasza skrzynka z narzędziami (ten folder)


def okrag_kasa(x, y):
    """Dopasowanie okręgu metodą najmniejszych kwadratów (Kåsa).
    Ta sama metoda co w programie LidarTreeSegmenter: program/10_pien_galezie_liscie.py."""
    A = np.column_stack([x, y, np.ones_like(x)])   # macierz N × 3: [x, y, 1]
    b = x * x + y * y                              # wektor N: x² + y²
    c, *_ = np.linalg.lstsq(A, b, rcond=None)      # rozwiązanie "najlepsze"
    cx, cy = c[0] / 2, c[1] / 2                    # środek okręgu
    r2 = c[2] + cx * cx + cy * cy                  # promień do kwadratu
    return cx, cy, np.sqrt(r2) if r2 > 0 else 0.0


# ---- 0. test na sztucznym pniu: widzimy tylko POŁOWĘ obwodu --------------
rng = np.random.default_rng(1)
kat = rng.uniform(0, np.pi, 300)                    # tylko 180° (jak z jednej strony)
xs = 5 + 0.20 * np.cos(kat) + rng.normal(0, 0.004, 300)
ys = 7 + 0.20 * np.sin(kat) + rng.normal(0, 0.004, 300)
cx, cy, r = okrag_kasa(xs, ys)
print(f"Test: sztuczny pień r = 20 cm, widać pół obwodu -> "
      f"wyszło r = {r * 100:.1f} cm, środek ({cx:.2f}, {cy:.2f})")

# ---- 1. wczytanie i wybór drzewa -----------------------------------------
sciezka = KW.sciezka_z_argumentu("python rozwiazanie_06_okrag.py plik.laz [nr_drzewa]")
chm = KW.wczytaj_chmure(sciezka)
nr = int(sys.argv[2]) if len(sys.argv) > 2 else None
nr, idx = KW.wybierz_drzewo(chm, nr)

xyz, h = chm["xyz"][idx], chm["h"][idx]

# ---- 2. plaster 1,3 m ± 5 cm ---------------------------------------------
w_plastrze = np.abs(h - 1.3) <= 0.05
if chm["czesc"] is not None:
    pien = w_plastrze & (chm["czesc"][idx] == 1)
    if pien.sum() >= 20:
        print("  biorę tylko punkty oznaczone jako pień (czesc = 1)")
        w_plastrze = pien
pl = xyz[w_plastrze]
print(f"Drzewo {nr}: punktów w plastrze 1,3 m: {len(pl)}")
if len(pl) < 10:
    sys.exit("Za mało punktów w plastrze, żeby dopasować okrąg. "
             "Wybierz inne drzewo (drugi argument).")

# ---- 3. dopasowanie: zwykłe i odporne -------------------------------------
cx, cy, r = okrag_kasa(pl[:, 0], pl[:, 1])
print(f"Kåsa (wszystkie punkty):   pierśnica = {2 * r * 100:.1f} cm")
odporny = KW.okrag_odporny(pl[:, 0], pl[:, 1])
if odporny:
    cx, cy, r = odporny
    print(f"Kåsa odporna (bez gałązek): pierśnica = {2 * r * 100:.1f} cm")
odl = np.hypot(pl[:, 0] - cx, pl[:, 1] - cy) - r      # + na zewnątrz, - w środku
print(f"Środek pnia: X = {cx:.2f}, Y = {cy:.2f}")
blad = np.sqrt(np.mean(odl ** 2))                     # średni błąd [m]
print(f"Średni błąd dopasowania: {blad * 100:.1f} cm")
if blad > 0.02 or r > 0.6:
    print("UWAGA: okrąg pasuje słabo (błąd > 2 cm albo pień grubszy niż 120 cm).\n"
          "       W plastrze są pewnie też krzewy, podszyt albo gałęzie.\n"
          "       Najlepiej użyj pliku <skan>_czesci.laz - tam pień jest\n"
          "       oznaczony (czesc = 1) i bierzemy tylko jego punkty.")
g = np.pi / 4 * (2 * r) ** 2
print(f"Pole przekroju g = {g:.4f} m²")

# ---- 4. porównanie z LidarTreeSegmenter (jeśli tabela leży obok) ------------------------
skan = chm["nazwa"].replace("_segmenty", "").replace("_czesci", "")
tab = Path(sciezka).resolve().parent.parent / "03_TABELE" / f"{skan}_czesci_drzewa.csv"
if tab.exists() and nr > 0:
    import pandas as pd
    t = pd.read_csv(tab).set_index("treeID")
    if nr in t.index:
        print(f"LidarTreeSegmenter podaje dla drzewa {nr}: "
              f"{t.loc[nr, 'srednica_13_m'] * 100:.1f} cm")

# ---- 5. obrazek: plaster z góry + okrąg -----------------------------------
fig, ax = plt.subplots(figsize=(6, 6))
ax.scatter((pl[:, 0] - cx) * 100, (pl[:, 1] - cy) * 100, s=3, c="#8b5a2b",
           label="punkty plastra 1,3 m")
t_ = np.linspace(0, 2 * np.pi, 200)
ax.plot(r * 100 * np.cos(t_), r * 100 * np.sin(t_), "r-", lw=1.5,
        label=f"okrąg, d = {2 * r * 100:.1f} cm")
ax.plot(0, 0, "r+")
ax.set_aspect("equal")
ax.set_xlabel("[cm]")
ax.set_ylabel("[cm]")
ax.set_title(f"Drzewo {nr} - plaster 1,3 m ± 5 cm z góry")
ax.grid(color="#ddd")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2)
wyniki = KW.folder_wynikow()
png = wyniki / f"{chm['nazwa']}_drzewo_{nr}_okrag.png"
fig.savefig(png, dpi=110, bbox_inches="tight")
print(f"Zapisano obrazek: {png}")
plt.show()          # na Windows otworzy okno z obrazkiem
