"""
LEKCJA 9 - ROZWIĄZANIE: tabela drzew w pandas i eksport do Excela
================================================================

Uruchomienie:
    python rozwiazanie_09_tabela.py <plik.laz>
    python rozwiazanie_09_tabela.py <plik.laz> buk      (gatunek domyślny)

Najlepiej na pliku <skan>_czesci.laz (pień jest tam oznaczony).
Zapisuje do wyniki_kursu:
    <skan>_tabela_drzew.xlsx   - arkusze "Drzewa" i "Podsumowanie"
    <skan>_tabela_drzew.csv    - to samo jako tekst (średnik, przecinek)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

import kurs_wspolne as KW

# pierśnicowa liczba kształtu grubizny f (jak w tablice_miazszosci.csv LidarTreeSegmenter)
LICZBA_KSZTALTU = {"świerk": 0.47, "buk": 0.51, "nieokreślony": 0.47}


def demo_bez_drzew():
    """Gdy chmura nie ma numerów drzew - pokazujemy pandas na małej tabelce."""
    print("\nTa chmura nie ma numerów drzew (surowy skan).")
    print("Pokażę pandas na tabelce z klupowania:\n")
    df = pd.DataFrame({
        "nr": [1, 2, 3, 4, 5, 6],
        "gatunek": ["świerk", "buk", "świerk", "buk", "świerk", "świerk"],
        "d13_cm": [32.5, 41.0, 18.2, 55.4, 36.3, 27.9],
        "h_m": [24.1, 26.5, 15.2, 29.0, 25.3, 21.7],
    })
    df["g_m2"] = np.pi / 4 * (df.d13_cm / 100) ** 2
    df["f"] = df.gatunek.map(LICZBA_KSZTALTU)
    df["v_m3"] = df.g_m2 * df.h_m * df.f
    print(df.round(3).to_string(index=False))
    print("\nSuma według gatunku:")
    print(df.groupby("gatunek")[["g_m2", "v_m3"]].sum().round(3))
    sys.exit(0)


# ---- 1. wczytanie --------------------------------------------------------
sciezka = KW.sciezka_z_argumentu("python rozwiazanie_09_tabela.py plik.laz [gatunek]")
gatunek_domyslny = sys.argv[2].lower() if len(sys.argv) > 2 else "świerk"
chm = KW.wczytaj_chmure(sciezka)
if chm["drzewo"] is None:
    demo_bez_drzew()

# ---- 2. tabela PUNKTÓW (tylko punkty drzew) -----------------------------
m = chm["drzewo"] > 0
if chm["czesc"] is not None:
    m &= chm["czesc"] != 4                     # bez podszytu
pkt = pd.DataFrame({
    "treeID": chm["drzewo"][m],
    "x": chm["xyz"][m, 0],
    "y": chm["xyz"][m, 1],
    "h": chm["h"][m].astype(np.float32),
})
print(f"\nTabela punktów: {len(pkt):,} wierszy".replace(",", " "))
print(pkt.head())

# ---- 3. groupby: jedna linijka na drzewo ---------------------------------
drzewa = pkt.groupby("treeID").agg(
    liczba_punktow=("h", "size"),
    wysokosc_m=("h", lambda s: s.quantile(0.999)),
    x=("x", "median"),
    y=("y", "median"),
)
print(f"\nDrzew: {len(drzewa)}")

# ---- 4. pierśnica: okrąg w plastrze 1,3 m każdego drzewa (lekcja 6) -------
w_plastrze = (np.abs(chm["h"] - 1.3) <= 0.05) & (chm["drzewo"] > 0)
if chm["czesc"] is not None:
    w_plastrze &= chm["czesc"] == 1            # tylko punkty pnia
plaster = pd.DataFrame({"treeID": chm["drzewo"][w_plastrze],
                        "x": chm["xyz"][w_plastrze, 0],
                        "y": chm["xyz"][w_plastrze, 1]})
d13, uwagi = {}, {}
for nr, grupa in plaster.groupby("treeID"):
    if len(grupa) < 20:
        uwagi[nr] = "za mało punktów na 1,3 m"
        continue
    x, y = grupa.x.to_numpy(), grupa.y.to_numpy()
    wynik = KW.okrag_odporny(x, y)
    if wynik is None:
        uwagi[nr] = "okrąg się nie dopasował"
        continue
    cx, cy, r = wynik
    blad = np.sqrt(np.mean((np.hypot(x - cx, y - cy) - r) ** 2))
    if blad > 0.02 or r > 0.6:
        uwagi[nr] = f"okrąg niepewny (błąd {blad * 100:.0f} cm)"
        continue
    d13[nr] = 2 * r * 100
drzewa["d13_cm"] = pd.Series(d13)
drzewa["uwagi"] = pd.Series(uwagi)
drzewa["uwagi"] = drzewa["uwagi"].fillna("")
brak = drzewa.d13_cm.isna() & (drzewa.uwagi == "")
drzewa.loc[brak, "uwagi"] = "brak punktów pnia na 1,3 m (pień zasłonięty?)"

# ---- 5. gatunek: z tabeli LidarTreeSegmenter (jeśli leży obok) albo domyślny ----------
drzewa["gatunek"] = gatunek_domyslny
skan = chm["nazwa"].replace("_segmenty", "").replace("_czesci", "")
tab = Path(sciezka).resolve().parent.parent / "03_TABELE" / f"{skan}_czesci_drzewa.csv"
if tab.exists():
    t = pd.read_csv(tab).dropna(subset=["treeID"]).set_index("treeID")
    if "gatunek" in t:
        rozp = t["gatunek"].reindex(drzewa.index)
        drzewa["gatunek"] = rozp.where(rozp.isin(["świerk", "buk"]),
                                       gatunek_domyslny)
        print(f"Gatunki wzięte z {tab.name}")
    if "srednica_13_m" in t:
        drzewa["d13_LidarTreeSegmenter_cm"] = (t["srednica_13_m"] * 100).reindex(drzewa.index)

# ---- 6. g, V = g · h · f ---------------------------------------------------
drzewa["g_m2"] = np.pi / 4 * (drzewa.d13_cm / 100) ** 2
drzewa["f"] = drzewa.gatunek.map(LICZBA_KSZTALTU).fillna(0.47)
drzewa["v_m3"] = drzewa.g_m2 * drzewa.wysokosc_m * drzewa.f

# drzewa niskie (< 5 m) to zwykle krzewy, podrost albo złomy - osobno
drzewa["do_sumy"] = (drzewa.wysokosc_m >= 5) & drzewa.d13_cm.notna()

print("\nPierwsze drzewa:")
print(drzewa[["liczba_punktow", "wysokosc_m", "d13_cm", "gatunek",
              "g_m2", "v_m3"]].head(10).round(3).to_string())

# ---- 7. podsumowanie na hektar --------------------------------------------
xyz = chm["xyz"]
pole_ha = (np.ptp(xyz[:, 0]) * np.ptp(xyz[:, 1])) / 10_000
licz = drzewa[drzewa.do_sumy]
podsum = licz.groupby("gatunek").agg(
    liczba_drzew=("v_m3", "size"),
    srednia_d13_cm=("d13_cm", "mean"),
    srednia_h_m=("wysokosc_m", "mean"),
    G_m2=("g_m2", "sum"),
    V_m3=("v_m3", "sum"),
)
podsum.loc["RAZEM"] = [len(licz), licz.d13_cm.mean(), licz.wysokosc_m.mean(),
                       licz.g_m2.sum(), licz.v_m3.sum()]
podsum["N_na_ha"] = podsum.liczba_drzew / pole_ha
podsum["G_m2_na_ha"] = podsum.G_m2 / pole_ha
podsum["V_m3_na_ha"] = podsum.V_m3 / pole_ha
print(f"\nPole prostokąta skanu: {pole_ha:.3f} ha (w przybliżeniu)")
print(podsum.round(2).to_string())

# ---- 8. zapis do Excela i CSV ---------------------------------------------
wyniki = KW.folder_wynikow()
xlsx = wyniki / f"{chm['nazwa']}_tabela_drzew.xlsx"
with pd.ExcelWriter(xlsx, engine="openpyxl") as excel:
    drzewa.round(3).to_excel(excel, sheet_name="Drzewa")
    podsum.round(2).to_excel(excel, sheet_name="Podsumowanie")
drzewa.round(3).to_csv(wyniki / f"{chm['nazwa']}_tabela_drzew.csv",
                       sep=";", decimal=",", encoding="utf-8-sig")
print(f"\nZapisano: {xlsx}")
