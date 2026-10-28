"""Etykiety gatunku zapisane skanerem w terenie (markPoint.csv).

Skaner ręczny pozwala w czasie chodzenia „oznaczyć” punkt przyciskiem
i wybrać kod, np. FI (Fichte = świerk) albo BU (Buche = buk). Plik
markPoint.csv leży w surowym folderze sesji (np. N0h_MT20260811-155717)
i ma współrzędne w tym samym układzie co chmura:

    "ProjectStartLocation";" LAT:47.98238";"LON:13.02729";...
    "20260811160035";"FI";"1.282557";"-11.94805";"4.24024"

Każdą etykietę przypisuję najbliższemu pniowi, jeśli leży bliżej niż
MAKS_ODL_M. Gdy jedna powierzchnia ma kilka sesji (kilka folderów),
biorę tę, której etykiety najlepiej trafiają w pnie - każda sesja może
mieć własny układ współrzędnych.
"""
import csv
import re
from pathlib import Path

import numpy as np

import lts_jezyk as J
import lts_uklad as U

MAKS_ODL_M = 1.0          # etykieta dalej od pnia nie jest przypisana
MIN_TRAFIEN = 0.5         # sesja musi trafić w pnie co najmniej połową
NAZWY = ("markpoint", "markpoints", "etykiety", "marks", "labels")

# kody z menu skanera (niemieckie skróty) i ich polskie / angielskie
# odpowiedniki -> gatunek wewnętrzny (po polsku)
KODY = {
    "FI": "świerk", "BU": "buk", "TA": "jodła", "KI": "sosna",
    "LA": "modrzew", "LÄ": "modrzew", "EI": "dąb", "BI": "brzoza",
    "ES": "jesion", "AH": "jawor", "BAH": "jawor", "ER": "olsza",
    "DG": "daglezja", "HB": "grab", "LI": "lipa", "PA": "topola",
    "KR": "czereśnia", "UL": "wiąz", "TAXUS": "cis",
    "EIB": "cis",
    "SW": "świerk", "ŚW": "świerk", "BK": "buk", "JD": "jodła",
    "SO": "sosna", "MD": "modrzew", "DB": "dąb", "BRZ": "brzoza",
    "JS": "jesion", "JW": "jawor", "OL": "olsza", "GB": "grab",
    "SP": "świerk", "BE": "buk", "FIR": "jodła", "PI": "sosna",
}


def gatunek_z_kodu(kod):
    """Kod etykiety -> gatunek wewnętrzny albo None (nieznany kod)."""
    k = str(kod).strip().strip('"').upper()
    if k in KODY:
        return KODY[k]
    g = J.gatunek_wew(k.lower())              # pełna nazwa: "świerk", "beech"
    return g if g in J.GATUNKI_EN and g not in (
        "nieokreślony", "nieokreślone") else None


# ----------------------------------------------------------------------
# szukanie
# ----------------------------------------------------------------------
def _sa_etykiety(folder):
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file()
                  and p.suffix.lower() in (".csv", ".txt")
                  and p.stem.lower() in NAZWY)


def kandydaci(kat, nazwa, plik_skanu=None):
    """Pliki etykiet, które mogą należeć do skanu (najpierw wyniki)."""
    import lts_sciezka as SC
    wyn = []
    rap = Path(kat) / U.RAPORT
    if rap.is_dir():
        wyn += sorted(rap.glob(f"{nazwa}_etykiety.*")) + \
            sorted(rap.glob(f"{nazwa}_labels.*"))
    if not plik_skanu:
        import json
        for j in (f"{nazwa}_ustawienia.json",
                  "ustawienia_kroku1_odczytane.json"):
            try:
                plik_skanu = json.loads(U.plik(kat, j).read_text(
                    encoding="utf-8")).get("plik")
                break
            except (OSError, ValueError):
                continue
    if plik_skanu:
        p = Path(plik_skanu)
        r = SC.rdzen(p.stem)
        wyn += _sa_etykiety(p.parent)
        # surowe foldery sesji: N0h_MT20260811-155717 obok folderu skanu
        for baza in (p.parent, p.parent.parent):
            if not baza.is_dir():
                continue
            for f in sorted(baza.iterdir()):
                if f.is_dir() and re.match(rf"_*{re.escape(r)}(_|$)",
                                           f.name.lower()):
                    wyn += _sa_etykiety(f)
    widziane, wyn2 = set(), []
    for p in wyn:
        if p.resolve() not in widziane:
            widziane.add(p.resolve())
            wyn2.append(p)
    return wyn2


# ----------------------------------------------------------------------
# odczyt
# ----------------------------------------------------------------------
def _liczba(s):
    return float(str(s).strip().strip('"').replace(",", "."))


def wczytaj(plik):
    """Lista etykiet: dict(kod, gatunek, x, y, z, czas). Wiersze, które nie
    są etykietami (nagłówek, ProjectStartLocation, puste), pomija."""
    tekst = Path(plik).read_bytes().decode("utf-8-sig", errors="replace")
    sep = ";" if tekst.count(";") >= tekst.count(",") else ","
    wyn = []
    for w in csv.reader(tekst.splitlines(), delimiter=sep):
        w = [c.strip() for c in w if c.strip() != ""]
        if len(w) < 4:
            continue
        # kod to pierwsze pole, które nie jest liczbą; za nim x y (z)
        try:
            i = next(i for i, c in enumerate(w) if not re.fullmatch(
                r"[-+]?\d+([.,]\d*)?([eE][-+]?\d+)?", c))
        except StopIteration:
            continue
        try:
            x, y = _liczba(w[i + 1]), _liczba(w[i + 2])
            z = _liczba(w[i + 3]) if len(w) > i + 3 else np.nan
        except (ValueError, IndexError):
            continue
        wyn.append({"kod": w[i], "gatunek": gatunek_z_kodu(w[i]),
                    "x": x, "y": y, "z": z,
                    "czas": w[0] if i > 0 else ""})
    return wyn


# ----------------------------------------------------------------------
# dopasowanie do drzew
# ----------------------------------------------------------------------
def dopasuj(etykiety, nr, xy, maks=MAKS_ODL_M):
    """Każdą etykietę -> najbliższy pień (bliżej niż maks). Zwraca
    (przypisane {nr: etykieta}, wszystkie etykiety z polami nr i odl).
    Dwie etykiety przy jednym drzewie: wygrywa późniejsza (poprawka)."""
    nr = np.asarray(nr)
    xy = np.asarray(xy, float)
    ok = np.isfinite(xy).all(axis=1)
    przyp, wszystkie = {}, []
    for e in etykiety:
        e = dict(e, nr=None, odl=np.nan)
        if ok.any():
            d = np.hypot(xy[ok, 0] - e["x"], xy[ok, 1] - e["y"])
            j = int(np.argmin(d))
            e["odl"] = float(d[j])
            if d[j] <= maks:
                e["nr"] = int(nr[ok][j])
        if e["nr"] is not None and e["gatunek"]:
            przyp[e["nr"]] = e
        wszystkie.append(e)
    return przyp, wszystkie


def dla_skanu(kat, nazwa, nr, xy, plik_skanu=None, cicho=False):
    """Etykiety pasujące do skanu albo None. dict: plik, przypisane
    {nr: etykieta}, wszystkie (lista), nieznane_kody (zbiór)."""
    najl = None
    for p in kandydaci(kat, nazwa, plik_skanu):
        try:
            et = wczytaj(p)
        except OSError:
            continue
        if not et:
            continue
        przyp, wsz = dopasuj(et, nr, xy)
        traf = sum(e["nr"] is not None for e in wsz) / len(wsz)
        if najl is None or traf > najl["trafienia"]:
            najl = {"plik": p, "przypisane": przyp, "wszystkie": wsz,
                    "trafienia": traf}
    if najl is None:
        return None
    wlasny = najl["plik"].parent.name == U.RAPORT
    if najl["trafienia"] < MIN_TRAFIEN and not wlasny:
        if not cicho:
            print(J.t(f"         etykiety gatunku {najl['plik']} nie trafiają "
                      f"w pnie ({najl['trafienia']:.0%}) - pomijam "
                      f"(inny układ współrzędnych?)",
                      f"         species labels {najl['plik']} do not hit "
                      f"the stems ({najl['trafienia']:.0%}) - skipped "
                      f"(different coordinate system?)"), flush=True)
        return None
    najl["nieznane_kody"] = sorted({e["kod"] for e in najl["wszystkie"]
                                    if not e["gatunek"]})
    if not cicho:
        n = len(najl["wszystkie"])
        print(J.t(f"         etykiety gatunku: {najl['plik'].parent.name}/"
                  f"{najl['plik'].name}, {n}, przypisane "
                  f"{len(najl['przypisane'])} drzewom",
                  f"         species labels: {najl['plik'].parent.name}/"
                  f"{najl['plik'].name}, {n}, assigned to "
                  f"{len(najl['przypisane'])} trees"), flush=True)
        if najl["nieznane_kody"]:
            print(J.t("         UWAGA: nieznane kody etykiet: "
                      + ", ".join(najl["nieznane_kody"]),
                      "         WARNING: unknown label codes: "
                      + ", ".join(najl["nieznane_kody"])), flush=True)
    return najl
