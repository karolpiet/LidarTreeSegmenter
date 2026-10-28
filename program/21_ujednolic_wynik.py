"""
UJEDNOLICENIE WYNIKU SEGMENTACJI - kazda metoda do jednego formatu
==================================================================

PO CO TO JEST
-------------
Kazde narzedzie zapisuje numer drzewa inaczej:

    tree_segmenter_tool   pole treeID_pred
    3DFin                 pole tree_ID (liczba z przecinkiem)
    TreeISO (CloudCompare) czesto w polu intensity albo final_segs
    SegmentAnyTree        PredInstance
    ForestFormer3D        instance_pred
    Segfix                FOLDER z osobnym plikiem na kazde drzewo

Ten skrypt robi z kazdego z nich JEDEN WSPOLNY FORMAT:

    LidarTreeSegmenter\\metody\\<metoda>\\<powierzchnia>.laz
        wspolrzedne X Y Z + pole treeID_pred (0 = punkt nie nalezy do drzewa)

i dopiero na takich plikach dziala porownanie (20_porownaj_segmentacje.py).

JAK URUCHOMIC
-------------
    python 21_ujednolic_wynik.py <plik albo folder> --metoda NAZWA --powierzchnia 9F

Przyklady:
    python 21_ujednolic_wynik.py ..\\tree_segmenter_tool\\results\\9F_segmented_segfix_2_r30\\9F_segmented_segfix_2_r30_segmenty.laz --metoda tree_segmenter_tool --powierzchnia 9F
    python 21_ujednolic_wynik.py ..\\DANE\\_3DFin_\\_S2o__r20.las --metoda 3DFin --powierzchnia So2
    python 21_ujednolic_wynik.py ..\\DANE\\TreeISO\\S2o_r20.las --metoda TreeISO --powierzchnia So2 --pole intensity

Gdy skrypt nie zgadnie, w ktorym polu jest numer drzewa, wypisze liste pol -
wybierz wlasciwe i podaj przez --pole.
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np

try:
    import laspy
except ImportError:
    sys.exit("BLAD: brak biblioteki laspy.\n"
             "      python -m pip install laspy lazrs")

TU = Path(__file__).resolve().parent       # LidarTreeSegmenter\\program
ROOT = TU.parent
ROZSZERZENIA = (".las", ".laz")

# Pola, w ktorych rozne narzedzia trzymaja numer drzewa - sprawdzane po kolei.
ZNANE_POLA = ("treeID_pred", "PredInstance", "instance_pred", "pred_instance",
              "final_segs", "tree_ID", "treeID", "TreeID", "tree_id",
              "instance", "segment_id", "init_segs")
WZOR_NUMERU = re.compile(r"_(?:tree|drzewo)[_-]?(\d+)", re.IGNORECASE)


def zapisz(sciezka, x, y, z, ident):
    naglowek = laspy.LasHeader(point_format=6, version="1.4")
    naglowek.scales = np.array([0.001, 0.001, 0.001])
    naglowek.offsets = np.floor([x.min(), y.min(), z.min()])
    naglowek.add_extra_dim(laspy.ExtraBytesParams(name="treeID_pred",
                                                  type=np.int32))
    out = laspy.LasData(naglowek)
    out.x, out.y, out.z = x, y, z
    out.treeID_pred = ident.astype(np.int32)
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    out.write(sciezka)


def z_pliku(plik, pole):
    las = laspy.read(str(plik))
    pola = [d.name for d in las.point_format.dimensions]
    if pole is None:
        pole = next((p for p in ZNANE_POLA if p in pola), None)
    if pole is None or pole not in pola:
        sys.exit(f"BLAD: nie wiem, w ktorym polu jest numer drzewa.\n"
                 f"      Pola w pliku: {', '.join(pola)}\n"
                 f"      Podaj wlasciwe przez --pole NAZWA")
    v = np.asarray(las[pole], dtype=np.float64)
    v = np.where(np.isfinite(v) & (v > 0), v, 0)
    print(f"  numer drzewa z pola: {pole}")
    return (np.asarray(las.x), np.asarray(las.y), np.asarray(las.z),
            np.round(v).astype(np.int64))


def z_folderu(folder):
    pliki = sorted(p for p in folder.iterdir()
                   if p.suffix.lower() in ROZSZERZENIA)
    if not pliki:
        sys.exit(f"BLAD: w {folder} nie ma plikow .las/.laz")
    X, Y, Z, I = [], [], [], []
    for nr, p in enumerate(pliki, start=1):
        m = WZOR_NUMERU.search(p.stem) or re.search(r"(\d+)\s*$", p.stem)
        tid = int(m.group(1)) if m else nr
        l = laspy.read(str(p))
        X.append(np.asarray(l.x)); Y.append(np.asarray(l.y))
        Z.append(np.asarray(l.z)); I.append(np.full(len(l.points), tid))
    print(f"  folder: {len(pliki)} plikow, numer drzewa z nazwy pliku")
    return (np.concatenate(X), np.concatenate(Y), np.concatenate(Z),
            np.concatenate(I).astype(np.int64))


def main():
    ap = argparse.ArgumentParser(description="Wynik segmentacji -> wspolny "
                                             "format LidarTreeSegmenter")
    ap.add_argument("zrodlo", type=Path, help="plik .las/.laz albo folder "
                                              "z plikami drzew")
    ap.add_argument("--metoda", required=True,
                    help="nazwa metody, np. 3DFin, TreeISO, SegmentAnyTree")
    ap.add_argument("--powierzchnia", required=True,
                    help="nazwa powierzchni, np. 9F albo So2")
    ap.add_argument("--pole", default=None,
                    help="pole z numerem drzewa (gdy nie zgadnie sam)")
    a = ap.parse_args()

    if a.zrodlo.is_dir():
        x, y, z, ident = z_folderu(a.zrodlo)
    elif a.zrodlo.is_file():
        x, y, z, ident = z_pliku(a.zrodlo, a.pole)
    else:
        sys.exit(f"BLAD: nie ma takiego pliku ani folderu: {a.zrodlo}")

    cel = ROOT / "metody" / a.metoda / f"{a.powierzchnia}.laz"
    zapisz(cel, x, y, z, ident)
    n_drz = len(np.unique(ident[ident > 0]))
    print(f"  punktow: {len(x):,}, drzew: {n_drz}, "
          f"bez drzewa: {(ident == 0).mean()*100:.1f}%")
    print(f"\n  zapisano: {cel}")
    print(f"  teraz:    python 20_porownaj_segmentacje.py {a.powierzchnia}")


if __name__ == "__main__":
    main()
