"""
LidarTreeSegmenter - ustawienia jednego skanu: klasa drzewostanu i gatunek powierzchni
=========================================================================

Okno LidarTreeSegmenter zapisuje wybór do 03_TABELE\\<skan>_ustawienia_lts.json,
a kroki 1-3 go odczytują. Klasy (młody / dojrzały) i ich parametry są
w pliku LidarTreeSegmenter\\klasy_drzewostanu.csv, który można zmieniać.

  klasa:   "auto" (z pierśnic wykrytych drzew), "młody", "dojrzały"
  gatunek: "auto" (rozpoznany z kształtu), "świerk", "buk"
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

import lts_jezyk as J

TU = Path(__file__).resolve().parent
KLASY = TU.parent / "klasy_drzewostanu.csv"
GRANICA_KLAS_CM = 20.0       # mediana pierśnic poniżej -> drzewostan młody

DOMYSLNE = {
    "młody": dict(opis="Drzewostan młody, pierśnice około 8–20 cm",
                  piersnica_od_cm=8, piersnica_do_cm=20, prog_piersnicy_cm=7,
                  wysokosc_krzewu_m=5, podszyt_do_m=1.5,
                  podszyt_odleglosc_m=0.6),
    "dojrzały": dict(opis="Drzewostan dojrzały, pierśnice powyżej 20 cm",
                     piersnica_od_cm=20, piersnica_do_cm=120,
                     prog_piersnicy_cm=7, wysokosc_krzewu_m=10,
                     podszyt_do_m=3.0, podszyt_odleglosc_m=1.0),
}


def klasy():
    k = {n: dict(v) for n, v in DOMYSLNE.items()}
    try:
        t = pd.read_csv(KLASY, sep=";", comment="#", encoding="utf-8-sig")
        for _, r in t.iterrows():
            n = str(r.klasa).strip()
            n = J.klasa_wew(n)
            k[n] = {c: (r[c] if c.startswith("opis") else float(str(r[c])
                                                       .replace(",", ".")))
                    for c in t.columns if c != "klasa" and pd.notna(r[c])}
    except (OSError, ValueError, KeyError):
        pass
    return k


OPIS_EN = {"młody": "Young stand, DBH about 8–20 cm",
           "dojrzały": "Mature stand, DBH above 20 cm"}


def opis(nazwa, par):
    """Opis klasy w bieżącym języku (kolumna opis albo opis_en)."""
    if J.EN:
        return par.get("opis_en") or OPIS_EN.get(nazwa) or par.get("opis", "")
    return par.get("opis", "")


def plik(kat, nazwa):
    return Path(kat) / "03_TABELE" / f"{nazwa}_ustawienia_lts.json"


def wczytaj(kat, nazwa):
    p = plik(kat, nazwa)
    for stara in ("lidarol", "xylem"):  # wyniki zapisane pod starszymi nazwami programu
        if p.exists():
            break
        p = p.with_name(f"{nazwa}_ustawienia_{stara}.json")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def zapisz(kat, nazwa, **zmiany):
    d = wczytaj(kat, nazwa)
    d.update({k: v for k, v in zmiany.items() if v is not None})
    p = plik(kat, nazwa)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


def klasa_skanu(kat, nazwa, dbh_m=None):
    """(nazwa klasy, parametry, czy wybrana automatycznie)."""
    u = wczytaj(kat, nazwa)
    k = klasy()
    wyb = J.klasa_wew(u.get("klasa", "auto"))
    if wyb in k:
        return wyb, k[wyb], False
    d = np.asarray(dbh_m if dbh_m is not None else [], float)
    d = d[np.isfinite(d) & (d > 0)]
    nazwa_k = "młody" if len(d) and np.median(d) * 100 < GRANICA_KLAS_CM \
        else "dojrzały"
    return nazwa_k, k.get(nazwa_k, DOMYSLNE[nazwa_k]), True


def gatunek_skanu(kat, nazwa):
    g = J.gatunek_wew(wczytaj(kat, nazwa).get("gatunek", "auto"))
    return None if g in ("", "auto") else g
