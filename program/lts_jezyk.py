"""
LidarTreeSegmenter - język programu: angielski (domyślnie) albo polski
=========================================================

Jeden kod, dwie wersje. Język wybiera zmienna środowiskowa LTS_LANG,
którą ustawia plik startowy:

  LidarTreeSegmenter.bat, DRAG_SCAN_HERE.bat        -> po angielsku (domyślnie)
  LidarTreeSegmenter_PL.bat, PRZECIAGNIJ_TU_SKAN.bat -> LTS_LANG=pl, po polsku

Programy uruchamiane z okna dziedziczą zmienną, więc cały przebieg
(okno, dziennik, Excel, GeoPackage, obrazki, widok 3D) jest w jednym
języku.

W kodzie teksty stoją parami obok siebie:  t("Gotowe.", "Done.")

Wartości zapisywane w plikach roboczych i czytane potem przez programy
(gatunek "świerk", klasa "młody", decyzja "krzew", kolumny w 03_TABELE)
zostają polskie w obu wersjach - tłumaczymy je dopiero przy pokazywaniu.
Pliki wpisywane przez użytkownika mogą mieć wartości po polsku albo po
angielsku (spruce, beech, tree, shrub, snag, young, mature) - funkcje
*_wew zamieniają je na wewnętrzne polskie.
"""

import os

JEZYK = "en" if os.environ.get("LTS_LANG", "en").strip().lower() \
    .startswith("en") else "pl"
EN = JEZYK == "en"
NAZWA = "LidarTreeSegmenter"          # nazwa programu pokazywana użytkownikowi


def t(pl, en):
    """Tekst w bieżącym języku."""
    return en if EN else pl


TAK = t("tak", "yes")

# --- gatunki i grupy (wewnętrznie po polsku) ----------------------------
GATUNKI_EN = {
    "świerk": "spruce", "buk": "beech", "jodła": "fir", "sosna": "pine",
    "modrzew": "larch", "dąb": "oak", "brzoza": "birch", "olsza": "alder",
    "jawor": "sycamore", "klon": "maple", "jesion": "ash", "grab": "hornbeam",
    "lipa": "lime", "topola": "poplar", "osika": "aspen", "wierzba": "willow",
    "daglezja": "Douglas fir", "czereśnia": "cherry", "wiąz": "elm",
    "cis": "yew", "inny": "other", "inne": "other",
    "iglaste": "coniferous", "liściaste": "broadleaved",
    "nieokreślony": "unspecified", "nieokreślone": "unspecified",
}
_GATUNKI_WEW = {v.lower(): k for k, v in GATUNKI_EN.items()}
_GATUNKI_WEW.update({
    "unspecified": "nieokreślony", "unknown": "nieokreślony",
    "other": "inny", "norway spruce": "świerk", "european beech": "buk",
    "silver fir": "jodła", "scots pine": "sosna", "conifer": "iglaste",
    "conifers": "iglaste", "broadleaf": "liściaste",
    "broadleaves": "liściaste", "deciduous": "liściaste",
    "swierk": "świerk", "jodla": "jodła", "dab": "dąb",
})


def gatunek(g):
    """Gatunek / grupa do pokazania (wewnętrzna nazwa -> bieżący język)."""
    if not EN or not isinstance(g, str):
        return g
    return GATUNKI_EN.get(g.strip().lower(), g)


def gatunek_wew(g):
    """Gatunek wpisany przez użytkownika (pl albo en) -> nazwa wewnętrzna."""
    s = str(g).strip().lower()
    return _GATUNKI_WEW.get(s, s)


# --- decyzje ze sprawdzania drzew i kontrola pnia -----------------------
DECYZJE_EN = {"drzewo": "tree", "krzew": "shrub", "złom": "snag"}
_DECYZJE_WEW = {"ok": "drzewo", "krzak": "krzew", "tree": "drzewo",
                "shrub": "krzew", "bush": "krzew", "snag": "złom",
                "broken": "złom"}


def decyzja_wew(d):
    s = str(d).strip().lower()
    return _DECYZJE_WEW.get(s, s)


KONTROLA_EN = {"ok": "ok", "krzew": "shrub", "złom": "snag",
               "niepewny": "uncertain", "brak pnia": "no stem",
               "duplikat": "duplicate"}
_KONTROLA_WEW = {v: k for k, v in KONTROLA_EN.items()}


def kontrola(k):
    return KONTROLA_EN.get(k, k) if EN and isinstance(k, str) else k


def kontrola_wew(k):
    s = str(k).strip()
    return _KONTROLA_WEW.get(s, s)


# --- klasy drzewostanu ----------------------------------------------------
KLASY_EN = {"młody": "young", "dojrzały": "mature", "auto": "auto"}
_KLASY_WEW = {"young": "młody", "mature": "dojrzały", "mlody": "młody",
              "dojrzaly": "dojrzały"}


def klasa(k):
    return KLASY_EN.get(k, k) if EN and isinstance(k, str) else k


def klasa_wew(k):
    s = str(k).strip()
    return _KLASY_WEW.get(s.lower(), s)


# --- wartości w tabelach wynikowych (GeoPackage, raport) -----------------
WARTOSCI_EN = dict(GATUNKI_EN, **KONTROLA_EN, **{
    "tak": "yes", "nie": "no", "pomiar": "measured",
    "rekonstrukcja": "reconstructed", "brak": "none",
    "nic": "none", "pien": "stem", "galezie": "branches",
    "ulistnienie": "foliage", "podszyt": "understory",
    "dobre": "good", "niepewne": "uncertain", "słabe": "weak",
})


def wartosci(df, kolumny=None):
    """Kopia tabeli do zapisu w bieżącym języku: kolumny przemianowane
    wg słownika kolumny, znane wartości tekstowe przetłumaczone."""
    if not EN:
        return df
    import pandas as pd
    df = df.copy()
    for c in df.columns:
        if not (pd.api.types.is_numeric_dtype(df[c])
                or pd.api.types.is_bool_dtype(df[c])):
            df[c] = df[c].map(lambda v: WARTOSCI_EN.get(v, v)
                              if isinstance(v, str) else v)
    return df.rename(columns=kolumny) if kolumny else df


def liczba(x, miejsc=1):
    """Liczba do tekstu: po polsku 1 234,5, po angielsku 1,234.5."""
    s = f"{x:,.{miejsc}f}"
    return s if EN else s.replace(",", " ").replace(".", ",")
