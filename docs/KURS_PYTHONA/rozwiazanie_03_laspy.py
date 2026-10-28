"""
LEKCJA 3 - ROZWIĄZANIE: czytamy plik .las / .laz biblioteką laspy
=================================================================

Uruchomienie:
    python rozwiazanie_03_laspy.py <plik.laz>

Najciekawiej na plikach z programu LidarTreeSegmenter:
    wyniki\\<skan>\\02_CHMURY\\<skan>_segmenty.laz   (treeID_pred, wys_nad_grunt)
    wyniki\\<skan>\\02_CHMURY\\<skan>_czesci.laz     (treeID, czesc, p_drewno)
ale zadziała też na zwykłym, surowym skanie.
"""

import sys
from pathlib import Path

import numpy as np

try:
    import laspy
except ImportError:
    sys.exit("BŁĄD: brak laspy. Zainstaluj: python -m pip install laspy lazrs")

NAZWY_CZESCI = {0: "nic (grunt / bez drzewa)", 1: "pień", 2: "gałęzie",
                3: "liście / igły", 4: "podszyt"}

# ---- 1. ścieżka z konsoli ------------------------------------------------
if len(sys.argv) < 2:
    sys.exit("BŁĄD: podaj plik .las/.laz, np.\n"
             "      python rozwiazanie_03_laspy.py C:\\skany\\skan.laz\n"
             "      (możesz przeciągnąć plik z Eksploratora do okna konsoli)")
sciezka = Path(sys.argv[1])
if not sciezka.exists():
    sys.exit(f"BŁĄD: nie ma pliku {sciezka}")

# ---- 2. sam nagłówek - szybko, bez czytania punktów ---------------------
with laspy.open(str(sciezka)) as plik:
    nag = plik.header
    print("=== NAGŁÓWEK ===")
    print("Wersja LAS:     ", nag.version)
    print("Format punktów: ", nag.point_format.id)
    print("Liczba punktów: ", f"{nag.point_count:,}".replace(",", " "))
    print("Skala (dokładność zapisu):", nag.scales, "m")
    print("Przesunięcie (offset):    ", nag.offsets)
    print("Zasięg min:", np.round(nag.mins, 2))
    print("Zasięg max:", np.round(nag.maxs, 2))

# ---- 3. całe punkty ------------------------------------------------------
print("\nWczytuję punkty ...", flush=True)
las = laspy.read(str(sciezka))
pola = list(las.point_format.dimension_names)
dodatkowe = list(las.point_format.extra_dimension_names)
print("Wszystkie pola:", ", ".join(pola))
print("Pola dodatkowe (dopisane przez program):",
      ", ".join(dodatkowe) if dodatkowe else "brak - to surowy skan")

# współrzędne w metrach (laspy sam mnoży przez skalę i dodaje offset)
x = np.asarray(las.x)
y = np.asarray(las.y)
z = np.asarray(las.z)
print(f"\nPierwszy punkt: x={x[0]:.3f}  y={y[0]:.3f}  z={z[0]:.3f}")
print(f"Surowa liczba całkowita X w pliku: {las.X[0]}  "
      f"(= ({x[0]:.3f} - offset) / skala)")
szer = x.max() - x.min()
dl = y.max() - y.min()
print(f"Prostokąt skanu: {szer:.1f} × {dl:.1f} m = {szer * dl / 10000:.3f} ha")
print(f"Gęstość: {len(x) / (szer * dl):,.0f} pkt/m²".replace(",", " "))

# ---- 4. numery drzew -----------------------------------------------------
pole_drzewa = None
for kandydat in ("treeID", "treeID_pred"):
    if kandydat in pola:
        pole_drzewa = kandydat
        break

if pole_drzewa:
    drzewo = np.asarray(las[pole_drzewa])
    numery = np.unique(drzewo[drzewo > 0])
    print(f"\nNumer drzewa w polu '{pole_drzewa}': {len(numery)} drzew "
          f"(numery {numery.min()} .. {numery.max()})")
    ile = np.bincount(drzewo[drzewo > 0])
    najw = int(np.argmax(ile))
    print(f"Najwięcej punktów ma drzewo {najw}: "
          f"{ile[najw]:,}".replace(",", " "))
    print(f"Punkty bez drzewa (0): {np.sum(drzewo <= 0):,}".replace(",", " "))
else:
    print("\nBrak numerów drzew (to normalne w surowym skanie).")

# ---- 5. części drzewa ----------------------------------------------------
if "czesc" in pola:
    czesc = np.asarray(las["czesc"])
    print("\nPodział na części (pole 'czesc'):")
    licznik = np.bincount(czesc, minlength=5)
    for kod, ile_pkt in enumerate(licznik):
        nazwa = NAZWY_CZESCI.get(kod, "?")
        print(f"  {kod} {nazwa:25s} {ile_pkt:>12,} pkt  "
              f"({ile_pkt / len(czesc) * 100:5.1f}%)".replace(",", " "))

if "p_drewno" in pola:
    p = np.asarray(las["p_drewno"])
    print(f"\np_drewno: średnio {p.mean():.2f}, punktów z p > 0,5: "
          f"{np.mean(p > 0.5) * 100:.1f}%")

# ---- 6. wysokość nad gruntem ---------------------------------------------
if "wys_nad_grunt" in pola:
    h = np.asarray(las["wys_nad_grunt"])
    print(f"\nWysokość nad gruntem: od {h.min():.2f} do {h.max():.2f} m")
    print(f"Najwyższy punkt (99,9 percentyl): {np.percentile(h, 99.9):.1f} m")
else:
    print(f"\nBrak pola wys_nad_grunt. Różnica wysokości w skanie: "
          f"{z.max() - z.min():.1f} m (z teren i drzewa razem)")
