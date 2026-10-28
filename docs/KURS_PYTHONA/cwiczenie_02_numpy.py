"""
LEKCJA 2 - ĆWICZENIE: tablice numpy jako chmura punktów
=======================================================

Uzupełnij miejsca TODO. Program działa też przed uzupełnieniem.

Uruchomienie:
    python cwiczenie_02_numpy.py                 (chmura sztuczna - "pień")
    python cwiczenie_02_numpy.py <plik.laz>      (prawdziwy skan)
"""

import sys

import numpy as np


def sztuczny_pien(n=5000, r=0.20, wysokosc=6.0):
    rng = np.random.default_rng(42)
    kat = rng.uniform(0, 2 * np.pi, n)
    z = rng.uniform(0, wysokosc, n)
    x = 10.0 + r * np.cos(kat) + rng.normal(0, 0.005, n)
    y = 20.0 + r * np.sin(kat) + rng.normal(0, 0.005, n)
    return np.column_stack([x, y, z])


if len(sys.argv) > 1:
    import laspy
    las = laspy.read(sys.argv[1])
    punkty = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                              np.asarray(las.z)])
    del las
else:
    punkty = sztuczny_pien()
    print("Nie podano pliku - używam sztucznego pnia.")

print("Kształt tablicy:", punkty.shape)

# TODO 1: wytnij kolumny x, y, z (punkty[:, 0] itd.)
x = punkty[:, 0]
y = None   # <- popraw
z = None   # <- popraw

# TODO 2: wypisz min i max każdej kolumny (np. x.min(), x.max())
print("   [TODO 2] wypisz zasięg X, Y i Z")

# TODO 3: policz środek chmury: punkty.mean(axis=0)
print("   [TODO 3] policz środek chmury")

# TODO 4: zrób maskę plastra 1,25-1,35 m od najniższego punktu
#         z_od_dolu = z - z.min()
#         maska = (z_od_dolu > 1.25) & (z_od_dolu < 1.35)
#         i wypisz, ile punktów jest w plastrze: maska.sum()
if z is None:
    print("   [TODO 4] najpierw uzupełnij TODO 1 (z = punkty[:, 2])")
else:
    print("   [TODO 4] zrób maskę plastra i policz punkty")

# TODO 5 (dla chętnych): średnia odległość punktów plastra od jego środka.
#         Dla sztucznego pnia powinno wyjść ok. 20 cm.
