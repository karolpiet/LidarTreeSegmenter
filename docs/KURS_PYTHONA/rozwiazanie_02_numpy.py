"""
LEKCJA 2 - ROZWIĄZANIE: tablice numpy jako chmura punktów
=========================================================

Uruchomienie:
    python rozwiazanie_02_numpy.py                 (chmura sztuczna - "pień")
    python rozwiazanie_02_numpy.py <plik.laz>      (prawdziwy skan)
"""

import sys

import numpy as np


def sztuczny_pien(n=5000, r=0.20, wysokosc=6.0):
    """Robi sztuczną chmurę: walec (pień) o promieniu r i wysokości 6 m,
    z odrobiną szumu - jak ze skanera."""
    rng = np.random.default_rng(42)              # generator liczb losowych
    kat = rng.uniform(0, 2 * np.pi, n)           # n losowych kątów
    z = rng.uniform(0, wysokosc, n)              # n losowych wysokości
    x = 10.0 + r * np.cos(kat) + rng.normal(0, 0.005, n)
    y = 20.0 + r * np.sin(kat) + rng.normal(0, 0.005, n)
    return np.column_stack([x, y, z])            # sklejamy w tablicę N × 3


# ---- 1. skąd wziąć punkty ------------------------------------------------
if len(sys.argv) > 1:
    import laspy                                 # szczegóły w lekcji 3
    las = laspy.read(sys.argv[1])
    punkty = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                              np.asarray(las.z)])
    del las
    print("Wczytano prawdziwy skan:", sys.argv[1])
else:
    punkty = sztuczny_pien()
    print("Nie podano pliku - używam sztucznego pnia (walec r = 20 cm).")

# ---- 2. kształt tablicy --------------------------------------------------
print("\nKształt tablicy:", punkty.shape, " (wiersze = punkty, kolumny = x y z)")
print("Typ liczb:", punkty.dtype)
print("Pierwsze 3 punkty:\n", punkty[:3])

# ---- 3. wycinanie (slicing) ----------------------------------------------
x = punkty[:, 0]          # wszystkie wiersze, kolumna 0
y = punkty[:, 1]
z = punkty[:, 2]
print("\nPierwszy punkt:", punkty[0])
print("Wysokość (z) pierwszego punktu:", punkty[0, 2])

# ---- 4. statystyki -------------------------------------------------------
print(f"\nX: od {x.min():.2f} do {x.max():.2f} m")
print(f"Y: od {y.min():.2f} do {y.max():.2f} m")
print(f"Z: od {z.min():.2f} do {z.max():.2f} m")
srodek = punkty.mean(axis=0)                     # średnia każdej kolumny
print("Środek chmury (średnia x, y, z):", np.round(srodek, 2))

# ---- 5. maski (filtry True/False) ---------------------------------------
z_od_dolu = z - z.min()                          # wysokość od najniższego punktu
maska = (z_od_dolu > 1.25) & (z_od_dolu < 1.35)  # plaster 1,25-1,35 m
plaster = punkty[maska]
print(f"\nW plastrze 1,25-1,35 m od dołu jest {maska.sum()} punktów "
      f"z {len(punkty)}")

# szerokość plastra: odległość punktów od środka plastra
if len(plaster) > 0:
    sx, sy = plaster[:, 0].mean(), plaster[:, 1].mean()
    odl = np.sqrt((plaster[:, 0] - sx) ** 2 + (plaster[:, 1] - sy) ** 2)
    print(f"Średnia odległość od środka plastra: {odl.mean() * 100:.1f} cm")
    if len(sys.argv) == 1:
        print("  (dla sztucznego pnia powinno wyjść ok. 20 cm = promień)")

# ---- 6. ile punktów wyżej niż 2 m nad najniższym ------------------------
wysokie = z_od_dolu > 2.0
print(f"Punktów wyżej niż 2 m nad najniższym: {wysokie.sum()} "
      f"({wysokie.mean() * 100:.1f}%)")
