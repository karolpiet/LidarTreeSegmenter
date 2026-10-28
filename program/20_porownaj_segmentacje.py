"""
POROWNANIE SEGMENTACJI Z TWOIM WZORCEM
======================================

Bierze wszystkie metody zapisane we wspolnym formacie:

    LidarTreeSegmenter\\metody\\<metoda>\\<powierzchnia>.laz      (pole treeID_pred)

i porownuje kazda z Twoja recznie poprawiona chmura z DANE\\tree_conected.
Na koncu wypisuje RANKING metod i zapisuje szczegoly do:

    LidarTreeSegmenter\\porownanie\\<powierzchnia>\\ranking.csv
    LidarTreeSegmenter\\porownanie\\<powierzchnia>\\<metoda>_drzewa.csv

JAK URUCHOMIC
-------------
    python 20_porownaj_segmentacje.py 9F
    python 20_porownaj_segmentacje.py So2

JAK TO LICZY - w trzech zdaniach
--------------------------------
1. Kazdy punkt wzorca dostaje numer drzewa z metody (od najblizszego punktu
   metody, jesli lezy blizej niz 3 cm).
2. Dla kazdej pary "Twoje drzewo - drzewo metody" liczymy IoU: czesc
   wspolna punktow przez sume. 1.0 = identyczne, 0 = nic wspolnego.
3. Pary laczymy jeden-do-jednego (algorytm wegierski). Para z IoU >= 0.5
   to TRAFIENIE. Twoje drzewo bez pary = PRZEOCZONE. Drzewo metody bez
   pary (zbudowane glownie z punktow Twoich drzew) = FALSZYWE.

Segmenty metody lezace glownie na punktach SPOZA wzorca (grunt, krzaki,
ktorych nie oznaczales) sa pomijane - nie da sie ich ocenic.

CO OZNACZAJA KOLUMNY RANKINGU
-----------------------------
    czulosc     ile Twoich drzew metoda znalazla (TP / wszystkie Twoje)
    precyzja    ile drzew metody jest prawdziwych (TP / wszystkie jej)
    F1          jedna liczba laczaca obie - im wyzej, tym lepiej
    sr_IoU      jak dokladnie trafione drzewa pokrywaja sie z Twoimi
    pkt_dobrze  jaki procent punktow wzorca trafil do wlasciwego drzewa
    pociete     Twoje drzewa rozbite na 2+ kawalki
    zlepione    drzewa metody, w ktorych siedza 2+ Twoje drzewa
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import laspy
    from scipy.optimize import linear_sum_assignment
    from scipy.spatial import cKDTree
except ImportError as e:
    sys.exit(f"BLAD: brak biblioteki ({e.name}).\n"
             "      python -m pip install laspy lazrs numpy pandas scipy")

TU = Path(__file__).resolve().parent       # LidarTreeSegmenter\\program
ROOT = TU.parent

# ---------------------------------------------------------------------
# TWOJE WZORCE (YOUR REFERENCES): recznie posegmentowane chmury z polem treeID.
# Dopisz tu kazda powierzchnie, np.:
#   "P1": ROOT / "wzorce" / "P1_reference.laz",
WZORCE = {
}
# ---------------------------------------------------------------------


def wczytaj(sciezka, pola):
    las = laspy.read(str(sciezka))
    nazwy = {d.name for d in las.point_format.dimensions}
    pole = next((p for p in pola if p in nazwy), None)
    if pole is None:
        sys.exit(f"BLAD: w {sciezka.name} nie ma pola {' / '.join(pola)}")
    xyz = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                           np.asarray(las.z)])
    ident = np.asarray(las[pole]).astype(np.int64)
    hag = np.asarray(las["hag"]) if "hag" in nazwy else None
    return xyz, ident, hag


def porownaj(ref_xyz, ref_id, ref_wys, met_xyz, met_id, a):
    # metoda przycieta do zasiegu wzorca (+1 m) - szybciej i mniej pamieci
    lo, hi = ref_xyz.min(axis=0) - 1, ref_xyz.max(axis=0) + 1
    w = np.all((met_xyz >= lo) & (met_xyz <= hi), axis=1)
    met_xyz, met_id = met_xyz[w], met_id[w]

    # 1. numer metody dla kazdego punktu wzorca
    odl, i = cKDTree(met_xyz).query(ref_xyz, distance_upper_bound=a.tolerancja,
                                    workers=-1)
    ok = np.isfinite(odl)
    pred = np.zeros(len(ref_xyz), np.int64)
    pred[ok] = met_id[i[ok]]

    # ktore segmenty metody leza GLOWNIE na Twoich drzewach
    odl2, _ = cKDTree(ref_xyz).query(met_xyz, distance_upper_bound=a.tolerancja,
                                     workers=-1)
    na_wzorcu = np.isfinite(odl2)
    s_id, s_all = np.unique(met_id[met_id > 0], return_counts=True)
    s_na = np.bincount(np.searchsorted(s_id, met_id[(met_id > 0) & na_wzorcu]),
                       minlength=len(s_id))
    oceniane = set(s_id[s_na / s_all >= 0.5].tolist())

    # 2. tablica czesci wspolnych
    r_ids, r_n = np.unique(ref_id, return_counts=True)
    p_ids = np.array(sorted(set(np.unique(pred[pred > 0]).tolist()) |
                            oceniane), dtype=np.int64)
    ri = np.searchsorted(r_ids, ref_id)
    m = pred > 0
    pi = np.searchsorted(p_ids, pred[m])
    wsp = np.zeros((len(r_ids), len(p_ids)))
    np.add.at(wsp, (ri[m], pi), 1)
    p_n = wsp.sum(axis=0)                     # punkty segmentu na wzorcu
    iou = wsp / (r_n[:, None] + p_n[None, :] - wsp + 1e-9)

    # 3. dopasowanie jeden-do-jednego
    rr, cc = linear_sum_assignment(-iou)
    traf = iou[rr, cc] >= a.min_iou
    tp = int(traf.sum())
    ocen_kol = np.isin(p_ids, list(oceniane))
    n_met = int(ocen_kol.sum())
    fp = n_met - int(np.isin(cc[traf], np.flatnonzero(ocen_kol)).sum())

    udz_r = wsp / r_n[:, None]                # czesc Twojego drzewa w segmencie
    udz_p = wsp / np.maximum(p_n[None, :], 1)
    pociete = int(((udz_r >= 0.2).sum(axis=1) >= 2).sum())
    zlepione = int(((udz_p >= 0.2) & (wsp >= 1000)).sum(axis=0)[ocen_kol]
                   .__ge__(2).sum())

    para = dict(zip(rr[traf], cc[traf]))
    drzewa = pd.DataFrame({
        "treeID": r_ids, "punktow": r_n, "wysokosc_m": ref_wys.reindex(r_ids).round(1).to_numpy(),
        "najlepszy_segment": p_ids[iou.argmax(axis=1)] if len(p_ids) else 0,
        "najlepsze_IoU": iou.max(axis=1).round(3) if len(p_ids) else 0,
        "trafione": [k in para for k in range(len(r_ids))],
        "IoU_pary": [round(iou[k, para[k]], 3) if k in para else np.nan
                     for k in range(len(r_ids))],
        "pociete": (udz_r >= 0.2).sum(axis=1) >= 2,
    })
    wys = drzewa.wysokosc_m >= a.wysokie
    n_ref = len(r_ids)
    prec = tp / max(tp + fp, 1)
    rec = tp / n_ref
    wynik = dict(
        drzew_wzorca=n_ref, drzew_metody=n_met, trafione=tp,
        przeoczone=n_ref - tp, falszywe=fp,
        czulosc=round(rec * 100, 1), precyzja=round(prec * 100, 1),
        F1=round(200 * prec * rec / max(prec + rec, 1e-9), 1),
        **{f"czulosc_wysokie_{a.wysokie:g}m": round(drzewa.trafione[wys].mean() * 100, 1),
           f"czulosc_niskie": round(drzewa.trafione[~wys].mean() * 100, 1)
           if (~wys).any() else np.nan},
        sr_IoU=round(float(np.nanmean(drzewa.IoU_pary)), 3) if tp else np.nan,
        pkt_dobrze=round(sum(wsp[k, c] for k, c in para.items()) / len(ref_xyz) * 100, 1),
        pkt_bez_punktu_metody=round((~ok).mean() * 100, 1),
        pociete=pociete, zlepione=zlepione)
    return wynik, drzewa


def main():
    ap = argparse.ArgumentParser(description="Porownanie segmentacji ze wzorcem")
    ap.add_argument("powierzchnia", help=f"jedna z: {', '.join(WZORCE)}")
    ap.add_argument("--tolerancja", type=float, default=0.03,
                    help="max odleglosc punktu metody od punktu wzorca [m]")
    ap.add_argument("--min-iou", type=float, default=0.5,
                    help="od jakiego IoU para liczy sie jako trafienie")
    ap.add_argument("--wysokie", type=float, default=10.0,
                    help="od jakiej wysokosci drzewo liczy sie jako wysokie [m]")
    a = ap.parse_args()

    if a.powierzchnia not in WZORCE:
        sys.exit(f"BLAD: nie znam powierzchni '{a.powierzchnia}'. "
                 f"Znane: {', '.join(WZORCE)} (dopisz nowa w WZORCE)")
    wz = WZORCE[a.powierzchnia]
    if not wz.is_file():
        sys.exit(f"BLAD: nie ma pliku wzorca: {wz}")
    pliki = sorted((ROOT / "metody").glob(f"*/{a.powierzchnia}.laz"))
    if not pliki:
        sys.exit(f"BLAD: brak metod dla {a.powierzchnia} w {ROOT / 'metody'}.\n"
                 f"      Najpierw: python 21_ujednolic_wynik.py ... "
                 f"--powierzchnia {a.powierzchnia}")

    print(f"Wzorzec: {wz.name}")
    ref_xyz, ref_id, hag = wczytaj(wz, ("treeID",))
    zz = hag if hag is not None else ref_xyz[:, 2]
    s = pd.DataFrame({"t": ref_id, "z": zz}).groupby("t").z
    ref_wys = (s.max() if hag is not None else s.max() - s.min())
    print(f"  {len(np.unique(ref_id))} drzew, {len(ref_xyz):,} punktow")

    katalog = ROOT / "porownanie" / a.powierzchnia
    katalog.mkdir(parents=True, exist_ok=True)
    wiersze = []
    for p in pliki:
        metoda = p.parent.name
        print(f"\n  metoda: {metoda}")
        met_xyz, met_id, _ = wczytaj(p, ("treeID_pred",))
        wynik, drzewa = porownaj(ref_xyz, ref_id, ref_wys, met_xyz, met_id, a)
        drzewa.to_csv(katalog / f"{metoda}_drzewa.csv", index=False)
        wiersze.append({"metoda": metoda, **wynik})
        print(f"    F1 {wynik['F1']}  czulosc {wynik['czulosc']}%  "
              f"precyzja {wynik['precyzja']}%  sr_IoU {wynik['sr_IoU']}")

    rank = pd.DataFrame(wiersze).sort_values("F1", ascending=False)
    rank.to_csv(katalog / "ranking.csv", index=False)
    print("\n" + "=" * 78)
    print(f"  RANKING - {a.powierzchnia}  (IoU >= {a.min_iou}, "
          f"tolerancja {a.tolerancja} m)")
    print("=" * 78)
    kol = ["metoda", "F1", "czulosc", "precyzja", "sr_IoU", "pkt_dobrze",
           "przeoczone", "falszywe", "pociete", "zlepione"]
    print(rank[kol].to_string(index=False))
    print(f"\n  szczegoly: {katalog}")
    if rank.pkt_bez_punktu_metody.max() > 20:
        print("\n  UWAGA: dla czesci metod ponad 20% punktow wzorca nie ma "
              "punktu metody w poblizu.\n  Zwykle znaczy to, ze metoda "
              "przerzedzila chmure albo pracowala w innym ukladzie "
              "wspolrzednych.\n  Patrz kolumna pkt_bez_punktu_metody w ranking.csv.")


if __name__ == "__main__":
    main()
