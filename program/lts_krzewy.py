"""Krzewy (podszyt) jako osobne obiekty.

Segmentacja z kroku 1 przypisuje każdy punkt roślinności do któregoś
drzewa, a krok 2 oznacza tylko część z nich jako podszyt (czesc = 4).
Ten moduł robi z tych punktów policzalne krzewy:

1. Kandydaci: punkty podszytu 0,3-4 m nad gruntem oraz niskie gałęzie
   i liście drzew, które mają wyraźną przerwę (co najmniej 1 m bez
   gałęzi) między dołem a koroną - w dojrzałym drzewostanie to krzaki
   przy pniu, nie korona. Pień zostaje nietknięty: punkty części „pień”
   i wszystko bliżej niż 15 cm od kory pnia nigdy nie jest krzewem.
2. Siatka 25 cm z góry. Komórka jest „krzewiasta”, gdy punkty zajmują
   co najmniej 3 warstwy po 25 cm między 0,5 a 3,25 m i najwyższy ma
   0,8 m - to bryła krzaka, nie sama trawa czy paprocie.
3. Sąsiednie komórki łączą się w płaty. Duży płat dzielę na krzewy
   według lokalnych wierzchołków (najwyższe miejsca co najmniej 1,25 m
   od siebie), każda komórka trafia do najbliższego wierzchołka.
4. Zostają krzewy o powierzchni co najmniej 0,5 m².

Wynik zapisuje się w 03_TABELE: <skan>_krzewy.csv (lista) i
<skan>_krzewy.npz (siatka z numerami, żeby widok 3D mógł pokolorować
punkty).
"""
from pathlib import Path

import laspy
import numpy as np
import pandas as pd
from scipy import ndimage as ndi

import lts_uklad as U

KOMORKA_M = 0.25        # siatka z góry
OD_M, DO_M = 0.3, 4.0   # pas wysokości krzewów nad gruntem
WARSTWA_M = 0.25        # grubość warstwy przy liczeniu bryły krzaka
MIN_WARSTW = 3          # tyle warstw 0,5-3,25 m musi być zajętych
MIN_WYS_M = 0.8         # najwyższy punkt komórki co najmniej tyle
MIN_POLE_M2 = 0.5       # mniejsze płaty pomijam
ODSTEP_WIERZCH_M = 1.25  # wierzchołki krzewów co najmniej tak daleko
OD_KORY_M = 0.15        # bliżej kory pnia - to pień, nie krzak
PRZERWA_M = 1.0         # pusty pas między dołem a koroną drzewa
PIEN, GALEZ, LISC, PODSZYT = 1, 2, 3, 4


# ----------------------------------------------------------------------
def os_pnia(okregi):
    """treeID -> (wysokości, środki x, środki y, promienie) posortowane."""
    wyn = {}
    if okregi is None or not len(okregi):
        return wyn
    o = okregi[okregi.srednica_m > 0].sort_values(["treeID", "wysokosc_m"])
    for t, g in o.groupby("treeID"):
        wyn[int(t)] = (g.wysokosc_m.to_numpy(float),
                       g.srodek_x.to_numpy(float), g.srodek_y.to_numpy(float),
                       g.srednica_m.to_numpy(float) / 2)
    return wyn


def odl_od_kory(xy, h, os_):
    """Pozioma odległość punktów od kory pnia (ujemna = w środku)."""
    H, X, Y, R = os_
    cx, cy, r = (np.interp(h, H, X), np.interp(h, H, Y), np.interp(h, H, R))
    return np.hypot(xy[:, 0] - cx, xy[:, 1] - cy) - r


def niskie_bez_korony(h_drzewa, wys_drzewa):
    """Czy niskie gałęzie / liście drzewa są oddzielone od korony pustym
    pasem co najmniej PRZERWA_M (wtedy to krzaki przy pniu)."""
    if not len(h_drzewa):
        return False
    k = 0.5
    biny = np.bincount(np.clip((h_drzewa / k).astype(int), 0, None),
                       minlength=int(wys_drzewa / k) + 2)
    prog = max(20, 0.001 * len(h_drzewa))
    zaj = biny >= prog
    od = int(DO_M / k)                  # przerwy szukam od 3-4 m w górę
    pusty = 0
    for b in range(int(1.0 / k), len(zaj)):
        if zaj[b]:
            if pusty * k >= PRZERWA_M and b * k >= 2.0:
                return True
            if b >= od + 2:             # korona zaczyna się nisko - nie
                return False
            pusty = 0
        else:
            pusty += 1
    return False


def kandydaci(xyz, h, drzewo, czesc, okregi):
    """Maska punktów, które mogą należeć do krzewów."""
    pas = (h >= OD_M) & (h <= DO_M) & (czesc != PIEN)
    m = pas & (czesc == PODSZYT)
    osie = os_pnia(okregi)
    # niskie gałęzie / liście drzew z przerwą pod koroną
    zl = np.flatnonzero(np.isin(czesc, (GALEZ, LISC)) & (drzewo > 0))
    if len(zl):
        o = np.argsort(drzewo[zl], kind="stable")
        zl = zl[o]
        gr = np.flatnonzero(np.diff(drzewo[zl])) + 1
        for idx in np.split(zl, gr):
            if niskie_bez_korony(h[idx], float(h[idx].max())):
                m[idx[pas[idx]]] = True
    # pień zawsze zostaje: nic bliżej niż OD_KORY_M od kory nie jest krzewem
    kand = np.flatnonzero(m & (drzewo > 0))
    if len(kand):
        o = np.argsort(drzewo[kand], kind="stable")
        kand = kand[o]
        gr = np.flatnonzero(np.diff(drzewo[kand])) + 1
        for idx in np.split(kand, gr):
            os_ = osie.get(int(drzewo[idx[0]]))
            if os_ is not None:
                bl = odl_od_kory(xyz[idx, :2], h[idx], os_) < OD_KORY_M
                m[idx[bl]] = False
    return m


def wykryj(xyz, h, drzewo, czesc, okregi=None):
    """Krzewy: (tabela, siatka) albo (pusta tabela, None)."""
    m = kandydaci(xyz, h, drzewo, czesc, okregi)
    pusta = pd.DataFrame(columns=["nr", "x", "y", "pole_m2", "wysokosc_m",
                                  "wysokosc_max_m", "punktow"])
    if m.sum() < 50:
        return pusta, None
    p, hh = xyz[m], h[m]
    x0, y0 = np.floor(p[:, 0].min()), np.floor(p[:, 1].min())
    i = ((p[:, 0] - x0) / KOMORKA_M).astype(int)
    j = ((p[:, 1] - y0) / KOMORKA_M).astype(int)
    nx, ny = int(i.max()) + 1, int(j.max()) + 1
    w = np.clip((hh / WARSTWA_M).astype(int), 0, int(DO_M / WARSTWA_M))
    zaj = np.zeros((nx, ny, w.max() + 1), bool)
    zaj[i, j, w] = True
    warstw = zaj[:, :, int(0.5 / WARSTWA_M):int(3.25 / WARSTWA_M) + 1].sum(2)
    hmax = np.zeros((nx, ny))
    np.maximum.at(hmax, (i, j), hh)
    kom = (warstw >= MIN_WARSTW) & (hmax >= MIN_WYS_M)
    kom = ndi.binary_opening(ndi.binary_closing(kom), iterations=1)
    lab, n = ndi.label(kom)
    if not n:
        return pusta, None
    # podział dużych płatów według wierzchołków
    hs = ndi.gaussian_filter(np.where(kom, hmax, 0), 1.0)
    rozm = int(round(ODSTEP_WIERZCH_M / KOMORKA_M)) * 2 + 1
    wierz = kom & (hs == ndi.maximum_filter(hs, size=rozm)) & (hs > 0)
    nr = np.zeros_like(lab)
    licz = 0
    for k in range(1, n + 1):
        maska = lab == k
        if maska.sum() * KOMORKA_M ** 2 < MIN_POLE_M2:
            continue
        wz = np.argwhere(maska & wierz)
        kom_k = np.argwhere(maska)
        if len(wz) <= 1:
            licz += 1
            nr[maska] = licz
            continue
        d = ((kom_k[:, None, :] - wz[None, :, :]) ** 2).sum(2)
        naj = d.argmin(1)
        for q in range(len(wz)):
            sel = kom_k[naj == q]
            if len(sel) * KOMORKA_M ** 2 < MIN_POLE_M2 / 2:
                # za mały kawałek - dołącz do sąsiada (najbliższy inny)
                continue
            licz += 1
            nr[sel[:, 0], sel[:, 1]] = licz
        # komórki z pominiętych kawałków -> najbliższy przypisany krzew
        bez = kom_k[nr[kom_k[:, 0], kom_k[:, 1]] == 0]
        z = kom_k[nr[kom_k[:, 0], kom_k[:, 1]] > 0]
        if len(bez) and len(z):
            dd = ((bez[:, None, :] - z[None, :, :]) ** 2).sum(2).argmin(1)
            nr[bez[:, 0], bez[:, 1]] = nr[z[dd, 0], z[dd, 1]]
    if not licz:
        return pusta, None
    # statystyki z punktów
    pn = nr[i, j]
    wiersze = []
    for k in range(1, licz + 1):
        s = pn == k
        if not s.any():
            continue
        kk = np.argwhere(nr == k)
        wiersze.append({
            "nr": k,
            "x": round(float(x0 + (kk[:, 0].mean() + 0.5) * KOMORKA_M), 2),
            "y": round(float(y0 + (kk[:, 1].mean() + 0.5) * KOMORKA_M), 2),
            "pole_m2": round(len(kk) * KOMORKA_M ** 2, 2),
            "wysokosc_m": round(float(np.percentile(hh[s], 95)), 2),
            "wysokosc_max_m": round(float(hh[s].max()), 2),
            "punktow": int(s.sum())})
    tab = pd.DataFrame(wiersze)
    siatka = {"x0": float(x0), "y0": float(y0), "krok": KOMORKA_M,
              "nr": nr.astype(np.int32)}
    return tab, siatka


def nr_punktow(xyz, h, siatka):
    """Numer krzewu dla punktów (0 = nie krzew) według zapisanej siatki;
    tylko w pasie wysokości krzewów."""
    if siatka is None:
        return np.zeros(len(xyz), np.int32)
    nr = siatka["nr"]
    i = np.floor((xyz[:, 0] - siatka["x0"]) / siatka["krok"]).astype(int)
    j = np.floor((xyz[:, 1] - siatka["y0"]) / siatka["krok"]).astype(int)
    ok = (i >= 0) & (j >= 0) & (i < nr.shape[0]) & (j < nr.shape[1]) & \
        (h >= OD_M) & (h <= DO_M)
    wyn = np.zeros(len(xyz), np.int32)
    wyn[ok] = nr[i[ok], j[ok]]
    return wyn


def obrys(siatka, k):
    """Obrys krzewu k jako wielokąt (otoczka wypukła rogów komórek)."""
    import lts_gpkg as G
    kk = np.argwhere(siatka["nr"] == k).astype(float)
    if not len(kk):
        return None
    s = siatka["krok"]
    rogi = np.concatenate([kk + d for d in ((0, 0), (1, 0), (0, 1), (1, 1))])
    xy = np.column_stack([siatka["x0"] + rogi[:, 0] * s,
                          siatka["y0"] + rogi[:, 1] * s])
    return G.otoczka(xy)


# ----------------------------------------------------------------------
# odczyt chmur i zapis wyników (krok 3: raport)
# ----------------------------------------------------------------------
def wysokosc_nad_gruntem(p_seg, n):
    """Pole wys_nad_grunt z *_segmenty.laz (kawałkami) albo None."""
    if not p_seg.exists():
        return None
    with laspy.open(str(p_seg)) as f:
        if f.header.point_count != n:
            return None
        pola = list(f.header.point_format.dimension_names)
        pole = next((p for p in ("wys_nad_grunt", "hag", "HeightAboveGround")
                     if p in pola), None)
        if not pole:
            return None
        return np.concatenate([np.asarray(ch[pole], np.float32)
                               for ch in f.chunk_iterator(4_000_000)])


def policz(kat, nazwa, cicho=False):
    """Wykrywa krzewy skanu i zapisuje tabelę i siatkę. Zwraca
    (tabela, siatka) albo (None, None), gdy brak danych. Gdy wynik jest
    nowszy od chmury, tylko go wczytuje."""
    import lts_jezyk as J
    p_cz = U.plik(kat, f"{nazwa}_czesci.laz")
    p_seg = U.plik(kat, f"{nazwa}_segmenty.laz")
    tab_dir = U.katalog(kat, U.TABELE)
    p_csv, p_npz = tab_dir / f"{nazwa}_krzewy.csv", tab_dir / f"{nazwa}_krzewy.npz"
    if not p_cz.exists():
        return None, None
    if p_csv.exists() and p_csv.stat().st_mtime > p_cz.stat().st_mtime \
            and Path(__file__).stat().st_mtime < p_csv.stat().st_mtime:
        return wczytaj(kat, nazwa)
    if not cicho:
        print(J.t("[KRZEWY] Szukam krzewów 0,3-4 m nad gruntem",
                  "[SHRUBS] Looking for shrubs 0.3-4 m above ground"),
              flush=True)
    las = laspy.read(str(p_cz))
    xyz = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                           np.asarray(las.z)])
    h = wysokosc_nad_gruntem(p_seg, len(xyz))
    if h is None:
        if not cicho:
            print(J.t("         brak wysokości nad gruntem - pomijam",
                      "         no height above ground - skipped"))
        return None, None
    drzewo = np.asarray(las.treeID).astype(np.int64)
    czesc = np.asarray(las.czesc).astype(np.uint8)
    del las
    p_ok = U.plik(kat, f"{nazwa}_pien_okregi.csv")
    okr = pd.read_csv(p_ok) if p_ok.exists() else None
    tab, siatka = wykryj(xyz, h, drzewo, czesc, okr)
    tab.to_csv(p_csv, index=False)
    if siatka is not None:
        np.savez_compressed(p_npz, **siatka)
    elif p_npz.exists():
        p_npz.unlink()
    if not cicho:
        print(J.t(f"         krzewów: {len(tab)}, razem "
                  f"{tab.pole_m2.sum() if len(tab) else 0:.1f} m²",
                  f"         shrubs: {len(tab)}, total "
                  f"{tab.pole_m2.sum() if len(tab) else 0:.1f} m²"),
              flush=True)
    return tab, siatka


def wczytaj(kat, nazwa):
    p_csv = U.plik(kat, f"{nazwa}_krzewy.csv")
    p_npz = U.plik(kat, f"{nazwa}_krzewy.npz")
    if not p_csv.exists():
        return None, None
    tab = pd.read_csv(p_csv)
    siatka = None
    if p_npz.exists():
        d = np.load(p_npz)
        siatka = {"x0": float(d["x0"]), "y0": float(d["y0"]),
                  "krok": float(d["krok"]), "nr": d["nr"]}
    return tab, siatka
