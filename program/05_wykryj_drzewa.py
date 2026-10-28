"""
LidarTreeSegmenter - krok 1: WYKRYWANIE DRZEW (tree_segmenter_tool + szukanie od góry)
=========================================================================

Uruchamia 02_detect_trees.py z tree_segmenter_tool BEZ zmian w jego kodzie,
z jednym dodatkiem: pnie szuka DWA RAZY.

  1. jak zwykle - plastry od 0,5 do 6 m nad gruntem,
  2. drugi raz WYŻEJ - od 2,5 do 8,5 m.

Po co: w gęstym podszycie dół pnia ginie w krzakach i pierwsze szukanie go
nie widzi. Kilka metrów wyżej strzała jest zwykle czysta. Pień znaleziony
tylko w drugim szukaniu, który nie pokrywa się z żadnym pniem z pierwszego,
jest dodawany jako nowe drzewo. Pierśnica takiego drzewa jest przedłużana
w dół ze zbieżności pnia i oznaczona w tabeli jako oszacowana.

Uzycie (zwykle robi to okno LidarTreeSegmenter):
  python 05_wykryj_drzewa.py <skan.laz> --wyniki ..\\wyniki
  python 05_wykryj_drzewa.py <skan.laz> --wyniki ..\\wyniki --bez-gory
  python 05_wykryj_drzewa.py <skan.laz> --wyniki ..\\wyniki --klasa młody

Klasa drzewostanu (młody / dojrzały, plik klasy_drzewostanu.csv) ustawia
zakres średnic pni, których szukamy, i próg pierśnicy. Bez niej (albo
"auto") zostają ustawienia tree_segmenter_tool dla wszystkich grubości.

Wszystkie inne opcje są przekazywane do 02_detect_trees.py.
"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TU = Path(__file__).resolve().parent       # LidarTreeSegmenter\program
ROOT = TU.parent
TST = ROOT / "tree_segmenter_tool"        # kopia w repozytorium
if not (TST / "02_detect_trees.py").exists():
    TST = ROOT.parent / "tree_segmenter_tool"   # stary uklad: folder obok
sys.path.insert(0, str(TU))
import lts_uklad as U                    # noqa: E402
import lts_na_zywo as Z                  # noqa: E402
import lts_ustawienia as UST             # noqa: E402
import lts_jezyk as J                    # noqa: E402

GORA_OD = 2.5        # drugie szukanie: od tej wysokości ...
GORA_DO = 8.5        # ... do tej [m nad gruntem]
ODL_DUPLIKATU = 0.5  # pień bliżej istniejącego niż tyle [m] = to samo drzewo


def wczytaj_02():
    spec = importlib.util.spec_from_file_location(
        "tst_02_detect_trees", TST / "02_detect_trees.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def okregi_lancucha(lan):
    """(wysokosc, x, y, promien) z lancucha okregow kroku 5."""
    return np.array([[o[1], o[2], o[3], o[4]] for o in lan]) if len(lan) \
        else np.zeros((0, 4))


def to_samo_drzewo(a, b, xy_a, xy_b):
    """Czy dwa lancuchy okregow opisuja ten sam pien."""
    if np.hypot(*(xy_a - xy_b)) < ODL_DUPLIKATU:
        return True
    if len(a) == 0 or len(b) == 0:
        return False
    # porownanie na wspolnych wysokosciach
    for h, x, y, r in b:
        bl = np.abs(a[:, 0] - h) < 0.13
        if bl.any():
            d = np.hypot(a[bl, 1] - x, a[bl, 2] - y)
            if (d < np.maximum(0.3, a[bl, 3] + r)).any():
                return True
    return False


def podepnij_podglad(m):
    """Podgląd na żywo w oknie LidarTreeSegmenter: opakowuje kroki 02 (bez zmian w
    jego kodzie) i po każdym zapisuje mały obraz chmury."""
    stan = {}

    def po(nazwa, f):
        def g(*a, **k):
            wynik = f(*a, **k)
            try:
                nazwa_kroku(nazwa, a, wynik)
            except Exception:                              # noqa: BLE001
                pass
            return wynik
        return g

    def nazwa_kroku(nazwa, a, wynik):
        if nazwa == "szum":
            pkt = wynik[0]
            Z.pokaz(J.t("Chmura po usunięciu szumu (kolor = wysokość)",
                        "Point cloud after noise removal (colour = "
                        "height)"), pkt,
                    pkt[:, 2] - np.percentile(pkt[:, 2], 1), "wysokosc")
        elif nazwa == "wys":
            stan["pkt"], stan["h"] = a[0], wynik[0]
            Z.pokaz(J.t("Wysokość nad gruntem (grunt odcięty)",
                        "Height above ground (ground removed)"), a[0],
                    wynik[0], "wysokosc")
        elif nazwa == "pnie":
            pnie, pkt, h = wynik[0], a[0], a[1]
            r = pnie.get("dbh_do_uzycia_m", pd.Series(np.nan, pnie.index)) \
                .astype(float).fillna(0.3).to_numpy() / 2
            ok = np.column_stack([pnie.x, pnie.y, r]) if len(pnie) else None
            Z.pokaz(J.t(f"Znalezione pnie: {len(pnie)}",
                        f"Stems found: {len(pnie)}"), pkt, h, "wysokosc", ok)
            stan["okregi"] = ok
        elif nazwa == "drzewa":
            Z.pokaz(J.t("Punkty przypisane do drzew (kolor = drzewo)",
                        "Points assigned to trees (colour = tree)"), a[0],
                    wynik, "drzewa", stan.get("okregi"))

    m.krok2_usun_szum = po("szum", m.krok2_usun_szum)
    m.krok4_normalizuj_wysokosc = po("wys", m.krok4_normalizuj_wysokosc)
    m.krok5b_sledz_pnie = po("pnie", m.krok5b_sledz_pnie)
    m.krok6b_przypisz_punkty_grafowo = po("drzewa",
                                          m.krok6b_przypisz_punkty_grafowo)
    m.krok6_przypisz_punkty = po("drzewa", m.krok6_przypisz_punkty)


def ustaw_klase(P, klasa, par):
    """Parametry 02 dla klasy drzewostanu (zakres pierśnic)."""
    P.MIN_SREDNICA_PNIA = min(P.MIN_SREDNICA_PNIA,
                              par["piersnica_od_cm"] * 0.6 / 100)
    P.MAX_SREDNICA_PNIA = min(P.MAX_SREDNICA_PNIA,
                              par["piersnica_do_cm"] * 2 / 100)
    P.MIN_DBH_RAPORTOWANIA = par["prog_piersnicy_cm"] / 100
    if klasa == "młody":
        P.MAX_ODLEGLOSC_OD_PNIA = min(P.MAX_ODLEGLOSC_OD_PNIA, 5.0)
    print(J.t(f"  Klasa drzewostanu: {klasa} ({par.get('opis', '')}): średnice "
              f"pni {P.MIN_SREDNICA_PNIA * 100:.0f}-"
              f"{P.MAX_SREDNICA_PNIA * 100:.0f} cm, próg pierśnicy "
              f"{P.MIN_DBH_RAPORTOWANIA * 100:.0f} cm",
              f"  Stand class: {J.klasa(klasa)} ({UST.opis(klasa, par)}): "
              f"stem diameters {P.MIN_SREDNICA_PNIA * 100:.0f}-"
              f"{P.MAX_SREDNICA_PNIA * 100:.0f} cm, DBH threshold "
              f"{P.MIN_DBH_RAPORTOWANIA * 100:.0f} cm"), flush=True)


def main():
    bez_gory = "--bez-gory" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--bez-gory"]
    klasa = None
    if "--klasa" in argv:
        i = argv.index("--klasa")
        klasa = J.klasa_wew(argv[i + 1])
        del argv[i:i + 2]
    m = wczytaj_02()
    P = m.P
    plik_ = Path(argv[0])
    wyn_ = Path(argv[argv.index("--wyniki") + 1]) if "--wyniki" in argv \
        else Path("results")
    kat_ = wyn_ / plik_.stem
    if klasa:
        UST.zapisz(kat_, plik_.stem, klasa=klasa)
    klasa = J.klasa_wew(UST.wczytaj(kat_, plik_.stem).get("klasa", "auto"))
    if klasa in UST.klasy():
        ustaw_klase(P, klasa, UST.klasy()[klasa])
    oryginal = m.krok5b_sledz_pnie
    info = {"z_gory": not bez_gory, "od": GORA_OD, "do": GORA_DO,
            "dodane": 0, "pni_z_dolu": None}

    def sledz_dwa_razy(punkty, wysokosc_ng):
        pnie, lan = oryginal(punkty, wysokosc_ng)
        info["pni_z_dolu"] = len(pnie)
        if bez_gory:
            return pnie, lan
        dol, gora = P.SLEDZENIE_DOL, P.SLEDZENIE_GORA
        print(J.t(f"\n[KROK 5] Szukam pni JESZCZE RAZ, wyzej ({GORA_OD}-"
                  f"{GORA_DO} m) - dla drzew, ktorych dol ginie w podszycie",
                  f"\n[STEP 5] Searching for stems AGAIN, higher up "
                  f"({GORA_OD}-{GORA_DO} m) - for trees whose base is hidden "
                  f"in the understory"), flush=True)
        try:
            P.SLEDZENIE_DOL, P.SLEDZENIE_GORA = GORA_OD, GORA_DO
            pnie2, lan2 = oryginal(punkty, wysokosc_ng)
        finally:
            P.SLEDZENIE_DOL, P.SLEDZENIE_GORA = dol, gora
        if len(pnie2) == 0:
            print(J.t("         wyzej nie ma nowych pni",
                      "         no new stems higher up"), flush=True)
            return pnie, lan
        A = [okregi_lancucha(l) for l in lan]
        xyA = pnie[["x", "y"]].to_numpy()
        nowe = []
        for j in range(len(pnie2)):
            b = okregi_lancucha(lan2[j])
            xyb = pnie2[["x", "y"]].to_numpy()[j]
            if not any(to_samo_drzewo(A[i], b, xyA[i], xyb)
                       for i in range(len(A))):
                nowe.append(j)
                A.append(b)
                xyA = np.vstack([xyA, xyb])
        info["dodane"] = len(nowe)
        print(J.t(f"         wyzej znaleziono {len(pnie2)} pni, z tego NOWYCH "
                  f"(niewidocznych z dolu): {len(nowe)}",
                  f"         found {len(pnie2)} stems higher up, of which "
                  f"NEW (not visible from below): {len(nowe)}"), flush=True)
        if not nowe:
            return pnie, lan
        pnie = pd.concat([pnie, pnie2.iloc[nowe]], ignore_index=True)
        lan = list(lan) + [lan2[j] for j in nowe]
        print(J.t(f"WYKRYTO DRZEW: {len(pnie)}",
                  f"TREES DETECTED: {len(pnie)}"), flush=True)
        return pnie, lan

    m.krok5b_sledz_pnie = sledz_dwa_razy
    if Z.wlaczony():
        podepnij_podglad(m)
    sys.argv = [str(TST / "02_detect_trees.py")] + argv
    m.main()

    # --- dopisanie znacznika do tabeli drzew ------------------------------
    plik = Path(argv[0])
    wyniki = Path(argv[argv.index("--wyniki") + 1]) if "--wyniki" in argv \
        else Path("results")
    przyrostek = argv[argv.index("--przyrostek") + 1] \
        if "--przyrostek" in argv else ""
    nazwa = plik.stem + przyrostek
    kat = wyniki / nazwa
    U.uporzadkuj(kat)
    tab_p = U.plik(kat, f"{nazwa}_drzewa.csv")
    if tab_p.exists() and info["pni_z_dolu"] is not None:
        tab = pd.read_csv(tab_p)
        tab["wykryto_z_gory"] = tab.id_drzewa > info["pni_z_dolu"]
        tab.to_csv(tab_p, index=False)
        info["dodane_w_tabeli"] = int(tab.wykryto_z_gory.sum())
    (U.katalog(kat, U.TABELE) / f"{nazwa}_szukanie_z_gory.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    if info["dodane"]:
        print(J.t(f"\n  Szukanie od gory dodalo {info['dodane']} drzew "
                  f"(kolumna wykryto_z_gory w tabeli drzew).",
                  f"\n  The search from above added {info['dodane']} trees "
                  f"(column wykryto_z_gory in the tree table)."))


if __name__ == "__main__":
    main()
