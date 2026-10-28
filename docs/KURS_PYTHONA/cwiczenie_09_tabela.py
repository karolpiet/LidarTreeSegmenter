"""
LEKCJA 9 - ĆWICZENIE: tabela drzew w pandas i eksport do Excela
==============================================================

Uruchomienie:
    python cwiczenie_09_tabela.py            (tylko część A - tabelka z klupowania)
    python cwiczenie_09_tabela.py <plik.laz> (część A i B - prawdziwy skan)
"""

import sys

import numpy as np
import pandas as pd

# ---- CZĘŚĆ A: tabelka z klupowania ---------------------------------------
df = pd.DataFrame({
    "nr": [1, 2, 3, 4, 5, 6],
    "gatunek": ["świerk", "buk", "świerk", "buk", "świerk", "świerk"],
    "d13_cm": [32.5, 41.0, 18.2, 55.4, 36.3, 27.9],
    "h_m": [24.1, 26.5, 15.2, 29.0, 25.3, 21.7],
})
print(df)

# TODO 1: dodaj kolumnę g_m2 = π/4 · (d13_cm / 100)²
# TODO 2: dodaj kolumnę f: świerk 0,47, buk 0,51
#         df["f"] = df.gatunek.map({"świerk": 0.47, "buk": 0.51})
# TODO 3: dodaj kolumnę v_m3 = g_m2 · h_m · f
# TODO 4: zsumuj G i V według gatunku: df.groupby("gatunek")[["g_m2", "v_m3"]].sum()
# TODO 5: zapisz tabelę do Excela: df.to_excel("wyniki_kursu/klupowanie.xlsx", index=False)
print("   [TODO 1-5] policz g, f, v, zsumuj po gatunku i zapisz do Excela")

# ---- CZĘŚĆ B: prawdziwy skan ---------------------------------------------
if len(sys.argv) > 1:
    import kurs_wspolne as KW
    chm = KW.wczytaj_chmure(KW.sciezka_z_argumentu())
    if chm["drzewo"] is None:
        sys.exit("Ta chmura nie ma numerów drzew - część B wymaga pliku z LidarTreeSegmenter.")
    m = chm["drzewo"] > 0
    pkt = pd.DataFrame({"treeID": chm["drzewo"][m], "h": chm["h"][m]})

    # TODO 6: policz dla każdego drzewa liczbę punktów i wysokość (max h):
    #         drzewa = pkt.groupby("treeID").agg(liczba=("h", "size"),
    #                                            wysokosc=("h", "max"))
    # TODO 7: wypisz 10 najwyższych drzew: drzewa.sort_values("wysokosc").tail(10)
    print("   [TODO 6-7] groupby po treeID")
