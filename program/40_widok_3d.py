"""
LidarTreeSegmenter - krok 4: WIDOK 3D (plik HTML)
====================================

Robi jeden plik HTML z chmurą punktów skanu do oglądania w 3D. Otwierasz
go dwuklikiem w przeglądarce (Chrome, Edge, Firefox), działa bez
internetu, można go wysłać mailem.

W przeglądarce:
  - lewy przycisk myszy obraca, prawy przesuwa, kółko przybliża,
  - kolor wg drzewa, wg części (pień / gałęzie / ulistnienie) albo wg
    wysokości,
  - kliknięcie w drzewo pokazuje jego numer, gatunek, pierśnicę,
    wysokość i miąższość, a przycisk „Tylko to drzewo” zostawia je samo,
  - na każdym pniu jest biały okrąg pierśnicy (1,3 m nad gruntem);
    kliknięte drzewo dostaje czerwony pierścień z podpisem pierśnicy,
  - drzewo można też wybrać z listy.

Żeby plik był lekki, chmura jest przerzedzona (domyślnie do 600 tys.
punktów; pień jest zostawiany gęściej niż korona).

Użycie (zwykle robi to okno LidarTreeSegmenter albo PRZECIAGNIJ_TU_SKAN.bat):
  python 40_widok_3d.py ..\\wyniki\\<skan>
  python 40_widok_3d.py ..\\wyniki\\<skan> --punktow 1000000
"""

import argparse
import base64
import json
import sys
from pathlib import Path

import laspy
import numpy as np
import pandas as pd

TU = Path(__file__).resolve().parent
sys.path.insert(0, str(TU))
import lts_uklad as U                    # noqa: E402
import lts_jezyk as J                    # noqa: E402
import lts_sciezka as SC                 # noqa: E402
import lts_dtm as DTM                    # noqa: E402
import lts_krzewy as KR                  # noqa: E402

JS = TU / "biblioteki_js"


def przerzedz(n_chce, maska, rng):
    idx = np.flatnonzero(maska)
    if len(idx) > n_chce:
        idx = rng.choice(idx, n_chce, replace=False)
    return idx


def b64(a):
    return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode("ascii")


PIERSNICA_M = 1.3          # wysokość pomiaru pierśnicy
ZASIEG_ANIMACJI_M = 10.0     # w animacji punkt „pojawia się”, gdy skaner
                             # przejdzie bliżej niż tyle metrów


def kolejnosc_odkrycia(xyz, sciezka, zasieg=ZASIEG_ANIMACJI_M, kom=1.0):
    """Dla każdego punktu: numer wierzchołka ścieżki, przy którym skaner
    pierwszy raz był bliżej niż `zasieg` (w poziomie). Liczone na siatce
    co `kom` m, żeby było szybko. Punkty nigdy niezbliżone: na końcu."""
    from scipy.spatial import cKDTree
    x0, y0 = xyz[:, 0].min(), xyz[:, 1].min()
    ix = ((xyz[:, 0] - x0) / kom).astype(np.int64)
    iy = ((xyz[:, 1] - y0) / kom).astype(np.int64)
    nx = ix.max() + 1
    k = iy * nx + ix
    kom_u, odw = np.unique(k, return_inverse=True)
    sr = np.column_stack([(kom_u % nx + 0.5) * kom + x0,
                          (kom_u // nx + 0.5) * kom + y0])
    drz = cKDTree(sciezka[:, :2])
    pierwszy = np.full(len(kom_u), len(sciezka) - 1, dtype=np.int64)
    for i, lst in enumerate(drz.query_ball_point(sr, zasieg)):
        if lst:
            pierwszy[i] = min(lst)
    return pierwszy[odw]


def siatka_terenu(plik, srodek, maks=180):
    """Model terenu przerzedzony do najwyżej `maks` komórek na bok,
    względem środka widoku; wysokości w cm i jasność cieniowania."""
    try:
        dtm = DTM.wczytaj(plik)
    except Exception:                              # noqa: BLE001
        return None
    if not dtm or not np.isfinite(dtm["Z"]).any():
        return None
    co = max(1, int(np.ceil(max(dtm["Z"].shape) / maks)),
             int(round(0.5 / dtm["krok"])))
    cien = DTM.cieniowanie(dtm)[::co, ::co]
    Z = DTM.gladki(dtm, 0.3)[::co, ::co]
    krok = dtm["krok"] * co
    ny, nx = Z.shape
    z = np.where(np.isfinite(Z), np.round((Z - srodek[2]) * 100), -32768)
    return {"nx": int(nx), "ny": int(ny), "krok": float(krok),
            "x0": round(dtm["x0"] + dtm["krok"] * 0.5 - srodek[0], 2),
            "y0": round(dtm["y0"] + dtm["krok"] * 0.5 - srodek[1], 2),
            "z": b64(np.clip(z, -32768, 32767).astype("<i2")),
            "c": b64(np.round(np.nan_to_num(cien, nan=0.7) * 255)
                     .astype(np.uint8))}


def wysokosc_piersnicy(h, xyz, drzewo):
    """Wysokość (z) plastra 1,3 m każdego drzewa: mediana z punktów drzewa,
    które mają 1,3 m ± 5 cm nad gruntem (pole wys_nad_grunt chmury
    *_segmenty.laz - to samo, od którego krok 2 mierzy pierśnicę)."""
    if h is None:
        return {}
    i = np.flatnonzero((np.abs(h - PIERSNICA_M) <= 0.05) & (drzewo > 0))
    wyn = {}
    if len(i):
        o = np.argsort(drzewo[i], kind="stable")
        t, z = drzewo[i][o], xyz[i[o], 2]
        gr = np.flatnonzero(np.diff(t)) + 1
        for tt, zz in zip(t[np.r_[0, gr]], np.split(z, gr)):
            if len(zz) >= 5:
                wyn[int(tt)] = float(np.median(zz))
    return wyn


def pierscienie(kat, nazwa, drzewa, xyz, drzewo, srodek, z13=None):
    """Okrąg pierśnicy na pniu: środek pnia na 1,3 m (z kroku 2), wysokość
    plastra 1,3 m z kroku 2 (z13; bez niego model terenu + 1,3 m) i promień
    z pierśnicy z raportu. Dopisuje
    do drzewa pole "pr" = [x, y, z, promień] względem środka widoku."""
    p_ok = U.plik(kat, f"{nazwa}_pien_okregi.csv")
    okr = pd.read_csv(p_ok) if p_ok.exists() else pd.DataFrame()
    dtm = DTM.wczytaj(U.plik(kat, f"{nazwa}_teren.npz"))
    kolej = np.argsort(drzewo, kind="stable")
    ds = drzewo[kolej]
    n = 0
    for t, d_ in drzewa.items():
        if not d_.get("d") or d_.get("k"):
            continue
        cx, cy = d_["x"] + srodek[0], d_["y"] + srodek[1]
        if len(okr):
            o = okr[(okr.treeID == t) & ((okr.wysokosc_m - PIERSNICA_M).abs()
                                         <= 0.3) & (okr.srednica_m > 0)]
            if len(o):
                w = (0.31 - (o.wysokosc_m - PIERSNICA_M).abs()).to_numpy()
                cx = float(np.average(o.srodek_x, weights=w))
                cy = float(np.average(o.srodek_y, weights=w))
        if not (np.isfinite(cx) and np.isfinite(cy)):
            continue
        z0 = np.nan
        if z13 and t in z13:
            z0 = z13[t] - PIERSNICA_M
        elif dtm:
            ny, nx = dtm["Z"].shape
            i = int((cx - dtm["x0"]) / dtm["krok"])
            j = int((cy - dtm["y0"]) / dtm["krok"])
            if 0 <= i < nx and 0 <= j < ny:
                z0 = dtm["Z"][j, i]
        if not np.isfinite(z0):                     # bez modelu terenu
            a, b = np.searchsorted(ds, t), np.searchsorted(ds, t, "right")
            if b - a < 10:
                continue
            z0 = float(np.percentile(xyz[kolej[a:b], 2], 1))
        d_["pr"] = [round(cx - srodek[0], 3), round(cy - srodek[1], 3),
                    round(z0 + PIERSNICA_M - srodek[2], 3),
                    round(d_["d"] / 200, 4)]
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=J.t(
        "Widok 3D chmury jako HTML", "3D view of the point cloud as HTML"))
    ap.add_argument("katalog", type=Path, help=J.t("folder wyników skanu",
                                                   "scan results folder"))
    ap.add_argument("--punktow", type=int, default=600_000,
                    help=J.t("ile punktów zostawić (domyślnie 600 000)",
                             "how many points to keep (default 600,000)"))
    a = ap.parse_args()
    kat = a.katalog.resolve()
    if kat.name in U.PODFOLDERY:
        kat = kat.parent
    nazwa = kat.name
    U.uporzadkuj(kat)

    p_cz = U.plik(kat, f"{nazwa}_czesci.laz")
    if not p_cz.exists():
        sys.exit(J.t(f"BLAD: brak {p_cz.name} - najpierw krok 2 (pień / "
                     f"gałęzie / ulistnienie)", f"ERROR: {p_cz.name} is "
                     f"missing - run step 2 (stem / branches / foliage) "
                     f"first"))
    print(J.t(f"[WIDOK 3D] Wczytuję {p_cz.name}",
              f"[3D VIEW] Loading {p_cz.name}"), flush=True)
    las = laspy.read(str(p_cz))
    xyz = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                           np.asarray(las.z)])
    drzewo = np.asarray(las.treeID).astype(np.int64)
    czesc = np.asarray(las.czesc).astype(np.uint8)
    h = KR.wysokosc_nad_gruntem(U.plik(kat, f"{nazwa}_segmenty.laz"),
                                len(xyz))
    z13 = wysokosc_piersnicy(h, xyz, drzewo)
    # krzewy z raportu (03_TABELE/<n>_krzewy.*): numer krzewu przy punkcie;
    # pień nigdy nie jest krzewem
    kr_tab, kr_siatka = KR.wczytaj(kat, nazwa)
    krz = np.zeros(len(xyz), np.uint16)
    if h is not None and kr_siatka is not None:
        krz = KR.nr_punktow(xyz, h, kr_siatka).astype(np.uint16)
        krz[czesc == 1] = 0
    del h

    rng = np.random.default_rng(0)
    N = a.punktow
    idx = np.concatenate([
        przerzedz(int(N * 0.25), (czesc == 1) & (drzewo > 0), rng),
        przerzedz(int(N * 0.67), (czesc > 1) & (drzewo > 0), rng),
        przerzedz(int(N * 0.08), drzewo <= 0, rng)])
    xyz, drzewo, czesc, krz = xyz[idx], drzewo[idx], czesc[idx], krz[idx]
    srodek = np.array([np.median(xyz[:, 0]), np.median(xyz[:, 1]),
                       np.percentile(xyz[:, 2], 0.5)])
    # ścieżka skanera (jeśli jest): linia w widoku i animacja przejazdu.
    # Punkty układamy w kolejności, w jakiej skaner mógł je zobaczyć, żeby
    # w animacji wystarczyło pokazywać coraz dłuższy początek tablicy.
    sc = SC.dla_skanu(kat, nazwa, xy_skanu=xyz[::97, :2])
    sciezka = odkryj = None
    if sc:
        sciezka = SC.uprosc(sc["xyz"], 0.25)
        kol = kolejnosc_odkrycia(xyz, sciezka)
        po = np.argsort(kol, kind="stable")
        xyz, drzewo, czesc, kol = xyz[po], drzewo[po], czesc[po], kol[po]
        krz = krz[po]
        odkryj = np.searchsorted(kol, np.arange(len(sciezka)),
                                 side="right")
        odkryj[-1] = len(kol)              # na końcu pokaż wszystko
    cm = np.clip(np.round((xyz - srodek) * 100), -32767, 32767) \
        .astype("<i2")
    print(J.t(f"         punktów w widoku: {len(idx):,}".replace(",", " "),
              f"         points in the view: {len(idx):,}"), flush=True)

    # dane drzew z raportu (gatunek, pierśnica, miąższość) albo z kroku 2
    drzewa = {}
    p_r = U.plik(kat, f"{nazwa}_drzewa_raport.csv")
    if p_r.exists():
        r = pd.read_csv(p_r)
        for _, w in r.iterrows():
            drzewa[int(w.nr)] = {
                "x": round(float(w.x - srodek[0]), 2),
                "y": round(float(w.y - srodek[1]), 2),
                "d": None if pd.isna(w.d13) else float(w.d13),
                "h": None if pd.isna(w.h) else float(w.h),
                "v": None if pd.isna(w.v) else float(w.v),
                "g": "" if pd.isna(w.grupa) else
                J.gatunek(J.gatunek_wew(w.grupa)),
                "gz": "" if pd.isna(w.get("grupa_zr")) else str(w.grupa_zr),
                "u": "" if pd.isna(w.get("d13_uw")) else str(w.d13_uw),
                "k": bool(w.get("krzew", False) is True or
                          str(w.get("krzew")) == "True"),
                "kc": "" if pd.isna(w.get("kontrola")) else
                J.kontrola_wew(w.kontrola),
                "s": str(w.get("sprawdzone", "")) in ("tak", "yes")}
    else:
        p_t = U.plik(kat, f"{nazwa}_czesci_drzewa.csv")
        if p_t.exists():
            r = pd.read_csv(p_t)
            for _, w in r.iterrows():
                drzewa[int(w.treeID)] = {
                    "x": round(float(w.pozycja_x - srodek[0]), 2),
                    "y": round(float(w.pozycja_y - srodek[1]), 2),
                    "d": None if pd.isna(w.srednica_13_m)
                    else round(float(w.srednica_13_m) * 100, 1),
                    "h": float(w.wysokosc_drzewa_m), "v": None,
                    "g": J.gatunek(str(w.get("gatunek", ""))), "gz": "",
                    "u": "",
                    "k": str(w.get("kontrola_pnia", "")) == "krzew"}

    # okręgi pierśnicy na pniach (widoczne w 3D z podpisem)
    pierscienie(kat, nazwa, drzewa, xyz, drzewo, srodek, z13)
    # obrazki drzew (przekrój 1,3 m) - do podglądu przy sprawdzaniu
    kat_obr = kat / U.OBRAZY
    obrazki = {}
    if kat_obr.exists():
        for f in kat_obr.glob("drzewo_*.png"):
            try:
                obrazki[int(f.stem.split("_")[1])] = f"../{U.OBRAZY}/{f.name}"
            except ValueError:
                pass
    for t, d_ in drzewa.items():
        d_["img"] = obrazki.get(t, "")
    dane = {"nazwa": nazwa, "n": int(len(idx)),
            "xyz": b64(cm), "drzewo": b64(drzewo.astype("<u2")),
            "czesc": b64(czesc), "drzewa": drzewa}
    if krz.any() and kr_tab is not None:
        dane["krz"] = b64(krz.astype("<u2"))
        dane["krzewy"] = {int(w.nr): {"h": float(w.wysokosc_m),
                                      "p": float(w.pole_m2)}
                          for _, w in kr_tab.iterrows()}
    if sc:
        dane["sciezka"] = np.round(sciezka - srodek, 2).tolist()
        dane["odkryj"] = odkryj.astype(int).tolist()
        dane["zasieg"] = ZASIEG_ANIMACJI_M
        # odległość wzdłuż ścieżki do każdego wierzchołka [m]
        dane["dyst"] = np.round(np.concatenate([[0], np.cumsum(
            np.linalg.norm(np.diff(sciezka, axis=0), axis=1))]), 2).tolist()
    # powierzchnia terenu z kroku 10 (03_TABELE/<n>_teren.npz)
    ter = siatka_terenu(U.plik(kat, f"{nazwa}_teren.npz"), srodek)
    if ter:
        dane["teren"] = ter
        print(J.t(f"         teren: siatka {ter['nx']} × {ter['ny']} "
                  f"co {ter['krok']:g} m",
                  f"         terrain: {ter['nx']} × {ter['ny']} grid, "
                  f"{ter['krok']:g} m"), flush=True)
    html = ((przetlumacz(SZABLON) if J.EN else SZABLON)
            .replace("@@PROG@@", J.NAZWA)
            .replace("@@THREE@@", (JS / "three.min.js")
                            .read_text(encoding="utf-8"))
            .replace("@@ORBIT@@", (JS / "OrbitControls.js")
                     .read_text(encoding="utf-8"))
            .replace("@@NAZWA@@", nazwa)
            .replace("@@DANE@@", json.dumps(dane, ensure_ascii=False)))
    wyj = U.katalog(kat, U.WIDOK) / U.nazwa_pliku("widok", nazwa)
    wyj.write_text(html, encoding="utf-8")
    # mały plik, który otwiera widok od razu w trybie sprawdzania drzew
    hasz = J.t("#sprawdzanie", "#review")
    (wyj.parent / U.nazwa_pliku("sprawdzanie", nazwa)).write_text(
        f'<!doctype html><meta charset="utf-8"><title>{J.NAZWA} - '
        + J.t("sprawdzanie", "tree review") +
        '</title><script>location.replace(' +
        json.dumps(wyj.name + hasz) + ')</script>'
        f'<a href="{wyj.name}{hasz}">' +
        J.t("Otwórz sprawdzanie drzew", "Open the tree review") + '</a>',
        encoding="utf-8")
    for r_ in ("widok", "sprawdzanie"):
        U.usun_inny_jezyk(kat, r_, nazwa)
    print(J.t(f"[WIDOK 3D] Zapisano: {wyj.name} "
              f"({wyj.stat().st_size / 1e6:.1f} MB) - otwórz dwuklikiem",
              f"[3D VIEW] Saved: {wyj.name} "
              f"({wyj.stat().st_size / 1e6:.1f} MB) - double-click to open"),
          flush=True)


SZABLON = r"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>@@PROG@@ 3D – @@NAZWA@@</title>
<style>
:root{--tlo:#14181a;--panel:#1d2326ee;--linia:#2c3438;--tekst:#e6ebe8;
--szary:#8a9691;--akcent:#7fb069;--drewno:#c8893b}
html,body{margin:0;height:100%;background:var(--tlo);color:var(--tekst);
font:14px "Segoe UI",system-ui,sans-serif;overflow:hidden}
#scena{position:fixed;inset:0}
.panel{position:fixed;background:var(--panel);border:1px solid var(--linia);
border-radius:8px;padding:12px 14px}
#menu{top:12px;left:12px;width:250px}
#menu h1{font-size:18px;margin:0 0 2px}
#menu .pod{color:var(--szary);font-size:12px;margin-bottom:10px}
.grupa{margin:10px 0 4px;color:var(--szary);font-size:12px}
button,select{background:#14181a;color:var(--tekst);border:1px solid var(--linia);
border-radius:5px;padding:5px 8px;font:inherit;font-size:13px;cursor:pointer}
button.wl{background:var(--akcent);color:#0e1210;border-color:var(--akcent)}
.rzad{display:flex;gap:6px;flex-wrap:wrap}
select{width:100%}
input[type=range]{width:100%}
#legenda{margin-top:8px;font-size:12px;color:var(--szary)}
#legenda span{display:inline-block;width:10px;height:10px;border-radius:2px;
margin:0 4px 0 8px;vertical-align:-1px}
#info{top:12px;right:12px;width:250px;display:none}
#info h2{margin:0 0 6px;font-size:17px}
#info table{width:100%;border-collapse:collapse;font-size:13px}
#info td{padding:3px 0;border-bottom:1px solid var(--linia)}
#info td:last-child{text-align:right}
#info .uw{color:#e0b070;font-size:12px;margin-top:6px}
#pomoc{left:12px;bottom:12px;color:var(--szary);font-size:12px;padding:6px 10px}
.nr{position:fixed;font-size:11px;color:#fff;background:#0009;padding:0 3px;
border-radius:3px;pointer-events:none;transform:translate(-50%,-100%)}
#pierLab{position:fixed;display:none;pointer-events:none;transform:translate(10px,-50%);
background:#000b;border-left:3px solid #ff3b30;border-radius:3px;padding:2px 7px;
font-size:13px;color:#fff;white-space:nowrap}
#pierLab small{color:var(--szary);font-size:11px}
#spr{right:12px;bottom:12px;width:380px;display:none;max-height:calc(100% - 40px);
overflow:auto}
#spr h2{margin:0 0 4px;font-size:17px}
#spr .lic{color:var(--szary);font-size:12px;margin-bottom:6px}
#spr img{width:100%;border-radius:4px;background:#fff;cursor:zoom-in;margin:6px 0}
#spr .przyc{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-top:6px}
#spr .przyc button{padding:7px 4px}
#spr .dec{margin-top:6px;font-size:13px;color:#e0b070;min-height:18px}
#spr .zapis{display:flex;gap:6px;margin-top:8px}
#duzy{position:fixed;inset:0;background:#000c;display:none;align-items:center;
justify-content:center;z-index:9;cursor:zoom-out}
#duzy img{max-width:96%;max-height:96%;background:#fff}
@media (max-width:640px){#menu{width:calc(100% - 52px)}#info{top:auto;bottom:12px;
width:calc(100% - 52px)}#pomoc{display:none}}
</style></head><body>
<div id="scena"></div>
<div id="numery"></div>
<div id="pierLab"></div>
<div class="panel" id="menu">
 <h1>@@PROG@@ 3D</h1><div class="pod">@@NAZWA@@ · <span id="ile"></span></div>
 <div class="grupa">Kolor</div>
 <div class="rzad">
  <button data-k="drzewo" class="wl">drzewa</button>
  <button data-k="czesc">pień / gałęzie / liście</button>
  <button data-k="wys">wysokość</button></div>
 <div id="legenda"></div>
 <div class="grupa">Drzewo</div>
 <select id="lista"><option value="">– wybierz drzewo –</option></select>
 <div class="rzad" style="margin-top:6px">
  <button id="tylko">Tylko to drzewo</button>
  <button id="wszystkie">Wszystkie</button></div>
 <div class="grupa">Wielkość punktów</div>
 <input type="range" id="rozmiar" min="1" max="6" step="0.5" value="2">
 <div class="rzad" style="margin-top:8px">
  <button id="numer">Numery drzew</button>
  <button id="pierscien" class="wl">Pierśnica na pniu</button>
  <button id="krzewy" class="wl">Krzewy widoczne</button>
  <button id="reset">Widok od nowa</button>
  <button id="sciezka" class="wl" style="display:none">Ścieżka skanera</button>
  <button id="teren" class="wl" style="display:none">Teren</button></div>
 <div id="przejazd" style="display:none">
 <div class="grupa">Przejazd skanera</div>
 <div class="rzad">
  <button id="odtworz">▶ Odtwórz przejazd</button>
  <button id="calosc">Cała chmura</button>
  <button id="sledz">Kamera za skanerem</button></div>
 <input type="range" id="suwak" min="0" max="1000" step="1" value="1000" style="margin-top:6px">
 <div class="pod" id="przejazdInfo"></div>
 <div class="pod" id="tempoOpis" style="margin-top:4px"></div>
 <input type="range" id="tempo" min="1" max="20" step="1" value="5"></div>
 <div class="grupa">Sprawdzanie</div>
 <button id="sprStart" style="width:100%">Sprawdź drzewa po kolei</button>
</div>
<div class="panel" id="spr">
 <h2 id="sprTyt"></h2><div class="lic" id="sprLic"></div>
 <div id="sprDane"></div>
 <img id="sprImg" alt="obrazek drzewa">
 <div class="przyc">
  <button data-d="drzewo">1 · Drzewo OK</button>
  <button data-d="krzew">2 · Krzak</button>
  <button data-d="złom">3 · Złom</button>
  <button data-g="świerk">4 · Świerk</button>
  <button data-g="buk">5 · Buk</button>
  <button id="sprPomin">→ · Pomiń</button></div>
 <div class="dec" id="sprDec"></div>
 <div class="zapis"><button id="sprWstecz">← Wstecz</button>
  <button id="sprZapisz" class="wl">Zapisz sprawdzenie</button>
  <button id="sprKoniec">Zakończ</button></div>
 <div class="lic" style="margin-top:6px">Zapisz plik w folderze wyników skanu,
 w 01_RAPORT, i przelicz raport (w oknie @@PROG@@ przycisk „Przelicz raport”).</div>
</div>
<div id="duzy"><img id="duzyImg" alt=""></div>
<div class="panel" id="info"></div>
<div class="panel" id="pomoc">lewy przycisk – obrót · prawy – przesuwanie ·
kółko – przybliżenie · kliknij drzewo, żeby zobaczyć dane</div>
<script>@@THREE@@</script>
<script>@@ORBIT@@</script>
<script>
const D = @@DANE@@;
function dek(s, T){const b=atob(s),u=new Uint8Array(b.length);
 for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return new T(u.buffer);}
const cm=dek(D.xyz,Int16Array), drz=dek(D.drzewo,Uint16Array),
      cz=dek(D.czesc,Uint8Array), N=D.n,
      krz=D.krz?dek(D.krz,Uint16Array):null, KRZ=D.krzewy||{};
const kp=i=>krz!==null&&krz[i]>0, FIOL=[.68,.42,.84];
document.getElementById('ile').textContent =
  Object.keys(D.drzewa).length+' drzew · '+(Object.keys(KRZ).length?Object.keys(KRZ).length+' krzewów · ':'')+N.toLocaleString('pl')+' punktów';
const pos=new Float32Array(N*3); let zmax=1;
for(let i=0;i<N*3;i++){pos[i]=cm[i]/100;}
for(let i=0;i<N;i++){if(pos[i*3+2]>zmax)zmax=pos[i*3+2];}
const scena=new THREE.Scene(); scena.background=new THREE.Color(0x14181a);
const kam=new THREE.PerspectiveCamera(50,innerWidth/innerHeight,0.1,2000);
kam.up.set(0,0,1);
const rend=new THREE.WebGLRenderer({antialias:false});
rend.setPixelRatio(Math.min(devicePixelRatio,2));
rend.setSize(innerWidth,innerHeight);
document.getElementById('scena').appendChild(rend.domElement);
const ster=new THREE.OrbitControls(kam,rend.domElement);
ster.enableDamping=true;
const geo=new THREE.BufferGeometry();
geo.setAttribute('position',new THREE.BufferAttribute(pos,3));
const kol=new Float32Array(N*3);
geo.setAttribute('color',new THREE.BufferAttribute(kol,3));
const mat=new THREE.PointsMaterial({size:2,vertexColors:true,sizeAttenuation:false});
const chmura=new THREE.Points(geo,mat); scena.add(chmura);
let tryb='drzewo', wybrane=null, tylko=false, krzewyWid=true;
// okręgi pierśnicy na pniach (1,3 m nad gruntem); wybrane drzewo dostaje
// czerwony pierścień i podpis z pierśnicą
let pierWid=true; const pierP=[], NO=48;
for(const t in D.drzewa){const d=D.drzewa[t]; if(!d.pr)continue; const [x,y,z,r]=d.pr;
 for(let i=0;i<NO;i++){const a=i/NO*Math.PI*2,b=(i+1)/NO*Math.PI*2;
  pierP.push(x+r*Math.cos(a),y+r*Math.sin(a),z,x+r*Math.cos(b),y+r*Math.sin(b),z);}}
const pierG=new THREE.BufferGeometry();
pierG.setAttribute('position',new THREE.BufferAttribute(new Float32Array(pierP),3));
const pierL=new THREE.LineSegments(pierG,new THREE.LineBasicMaterial({color:0xffffff,
 transparent:true,opacity:0.75})); scena.add(pierL);
const pierT=new THREE.Mesh(new THREE.TorusGeometry(1,0.07,8,64),
 new THREE.MeshBasicMaterial({color:0xff3b30})); pierT.visible=false; scena.add(pierT);
const PL=document.getElementById('pierLab');
function pierscien(){const d=wybrane!==null?D.drzewa[wybrane]:null;
 pierL.visible=pierWid&&!tylko;
 if(pierWid&&d&&d.pr){const [x,y,z,r]=d.pr, R=r*1.06+0.01;
  pierT.position.set(x,y,z); pierT.scale.set(R,R,R); pierT.visible=true;
  PL.innerHTML='pierśnica <b>'+d.d.toLocaleString('pl',{minimumFractionDigits:1,maximumFractionDigits:1})+
   ' cm</b><br><small>1,3 m nad gruntem</small>'; PL.style.display='block';}
 else{pierT.visible=false;PL.style.display='none';}}
function wPlastrze(i,t){const d=D.drzewa[t];
 return d&&d.pr&&Math.abs(pos[i*3+2]-d.pr[2])<=0.05;}
const KCZ=[[.29,.33,.31],[.78,.54,.23],[.88,.69,.44],[.50,.69,.41],[.55,.58,.70]];
function hsl(h,s,l){const c=new THREE.Color();c.setHSL(h,s,l);return [c.r,c.g,c.b];}
function kolDrzewa(t){if(t===0)return [.29,.33,.31];
 const g=(t*0.61803)%1; return hsl(g,.65,.55);}
function wiridis(f){const s=[[.27,.00,.33],[.23,.32,.55],[.13,.57,.55],[.37,.79,.38],[.99,.91,.14]];
 f=Math.max(0,Math.min(.999,f))*4; const i=Math.floor(f),r=f-i;
 return s[i].map((v,j)=>v+(s[i+1][j]-v)*r);}
function jestKrzew(t){const d=D.drzewa[t];return d&&d.k;}
function koloruj(){
 for(let i=0;i<N;i++){const t=drz[i]; let c;
  if(kp(i)&&tryb!=='wys')c=FIOL;
  else if(tryb==='czesc')c=KCZ[Math.min(cz[i],4)];
  else if(tryb==='wys')c=wiridis(pos[i*3+2]/zmax);
  else c=jestKrzew(t)?[.55,.45,.6]:kolDrzewa(t);
  let jas=1;
  if(wybrane!==null&&(t!==wybrane||kp(i)))jas=tylko?0:0.25;
  else if(pierWid&&wybrane!==null&&wPlastrze(i,t))c=[1,.42,.36];
  if(!krzewyWid&&(jestKrzew(t)||kp(i)))jas=0;
  kol[i*3]=c[0]*jas;kol[i*3+1]=c[1]*jas;kol[i*3+2]=c[2]*jas;}
 geo.attributes.color.needsUpdate=true;
 // ukryte punkty (czarne) przesuwamy poza widok przez rozmiar 0 w buforze pozycji
 const p=geo.attributes.position.array;
 for(let i=0;i<N;i++){const ukryj=(tylko&&wybrane!==null&&(drz[i]!==wybrane||kp(i)))||
   (!krzewyWid&&(jestKrzew(drz[i])||kp(i)));
  p[i*3+2]=ukryj?-9999:cm[i*3+2]/100;}
 geo.attributes.position.needsUpdate=true;
 legenda(); pierscien();}
function legenda(){const L=document.getElementById('legenda');
 if(tryb==='czesc')L.innerHTML='<span style="background:#c78a3b"></span>pień'+
  '<span style="background:#e0b070"></span>gałęzie<span style="background:#7fb069"></span>ulistnienie'+
  '<span style="background:#8c94b3"></span>podszyt';
 else if(tryb==='wys')L.innerHTML='nisko <span style="background:#440054"></span>'+
  '<span style="background:#21918c"></span><span style="background:#fde725"></span> wysoko ('+zmax.toFixed(0)+' m)';
 else L.innerHTML='każde drzewo ma swój kolor<br><span style="background:#8c7399"></span>krzew (pominięty w wynikach)';
 if(krz!==null&&tryb!=='wys')L.innerHTML+='<br><span style="background:#ad6bd6"></span>krzewy 0,3–4 m (podszyt)';}
function pokazKrzew(k){const I=document.getElementById('info'),d=KRZ[k];
 if(!d){I.style.display='none';return;}
 const f=(v,n,j)=>v.toLocaleString('pl',{minimumFractionDigits:n,maximumFractionDigits:n})+' '+j;
 I.innerHTML='<h2>Krzew '+k+'</h2><table>'+
  '<tr><td>Wysokość</td><td>'+f(d.h,1,'m')+'</td></tr>'+
  '<tr><td>Pole z góry</td><td>'+f(d.p,1,'m²')+'</td></tr></table>'+
  '<div class="uw" style="color:#c9a6e0">Krzew nie wchodzi do drzew ani miąższości.</div>';
 I.style.display='block';}
function pokazInfo(t){const I=document.getElementById('info'),d=D.drzewa[t];
 if(!t||!d){I.style.display='none';return;}
 const f=(v,n,j)=>v===null||v===undefined||Number.isNaN(v)?'–':v.toLocaleString('pl',{minimumFractionDigits:n,maximumFractionDigits:n})+' '+j;
 I.innerHTML='<h2>Drzewo '+t+'</h2><table>'+
  '<tr><td>Gatunek</td><td>'+(d.g||'–')+'</td></tr>'+
  (d.gz?'<tr><td>skąd</td><td>'+d.gz+'</td></tr>':'')+
  '<tr><td>Pierśnica</td><td>'+f(d.d,1,'cm')+'</td></tr>'+
  '<tr><td>Wysokość</td><td>'+f(d.h,1,'m')+'</td></tr>'+
  '<tr><td>Miąższość grubizny</td><td>'+f(d.v,3,'m³')+'</td></tr></table>'+
  (d.k?'<div class="uw">Prawdopodobnie krzew – pominięty w wynikach.</div>':'')+
  (d.u&&!d.k?'<div class="uw">'+d.u+'</div>':'');
 I.style.display='block';}
function wybierz(t,lec){wybrane=t;pokazInfo(t);
 document.getElementById('lista').value=t===null?'':t; koloruj();
 if(lec&&t!==null&&D.drzewa[t]){const d=D.drzewa[t],h=(d.h||15);
  ster.target.set(d.x,d.y,h/2);
  kam.position.set(d.x+h*0.9,d.y-h*0.9,h*0.8);}}
const lista=document.getElementById('lista');
Object.keys(D.drzewa).map(Number).sort((a,b)=>a-b).forEach(t=>{
 const d=D.drzewa[t],o=document.createElement('option');o.value=t;
 o.textContent='Drzewo '+t+(d.g&&d.g!=='nieokreślony'?' · '+d.g:'')+
  (d.d?' · '+d.d.toFixed(0)+' cm':'')+(d.k?' · krzew':'');lista.appendChild(o);});
lista.onchange=()=>wybierz(lista.value===''?null:Number(lista.value),true);
document.querySelectorAll('[data-k]').forEach(b=>b.onclick=()=>{
 tryb=b.dataset.k;document.querySelectorAll('[data-k]').forEach(x=>x.classList.toggle('wl',x===b));koloruj();});
document.getElementById('tylko').onclick=()=>{if(wybrane!==null){tylko=true;koloruj();}};
document.getElementById('wszystkie').onclick=()=>{tylko=false;wybierz(null,false);};
document.getElementById('rozmiar').oninput=e=>{mat.size=Number(e.target.value);};
const bK=document.getElementById('krzewy');
bK.onclick=()=>{krzewyWid=!krzewyWid;bK.classList.toggle('wl',krzewyWid);
 bK.textContent=krzewyWid?'Krzewy widoczne':'Krzewy ukryte';koloruj();};
let numery=false; const bN=document.getElementById('numer'), NR=document.getElementById('numery');
bN.onclick=()=>{numery=!numery;bN.classList.toggle('wl',numery);NR.innerHTML='';
 if(numery)Object.keys(D.drzewa).forEach(t=>{const e=document.createElement('div');
  e.className='nr';e.textContent=t;e.dataset.t=t;NR.appendChild(e);});};
const bP=document.getElementById('pierscien');
if(!pierP.length)bP.style.display='none';
bP.onclick=()=>{pierWid=!pierWid;bP.classList.toggle('wl',pierWid);koloruj();};
function widokStart(){let r=0;for(const t in D.drzewa){const d=D.drzewa[t];
  if(Number.isFinite(d.x)&&Number.isFinite(d.y))r=Math.max(r,Math.hypot(d.x,d.y));}
 r=Math.max(r,10);
 ster.target.set(0,0,zmax*0.35);kam.position.set(r*1.4,-r*1.4,zmax*1.1);}
document.getElementById('reset').onclick=widokStart; widokStart();
// powierzchnia terenu (model z punktów gruntu) - półprzezroczysta
if(D.teren){const T=D.teren, tz=dek(T.z,Int16Array), tc=dek(T.c,Uint8Array),
  nx=T.nx, ny=T.ny, BR=-32768;
 const P=new Float32Array(nx*ny*3), C=new Float32Array(nx*ny*3), I=[];
 for(let j=0;j<ny;j++)for(let i=0;i<nx;i++){const k=j*nx+i;
  P[k*3]=T.x0+i*T.krok;P[k*3+1]=T.y0+j*T.krok;
  P[k*3+2]=tz[k]===BR?0:tz[k]/100-0.03;
  const sw=0.35+0.65*tc[k]/255;C[k*3]=0.62*sw;C[k*3+1]=0.47*sw;C[k*3+2]=0.30*sw;}
 for(let j=0;j<ny-1;j++)for(let i=0;i<nx-1;i++){const a=j*nx+i,b=a+1,c=a+nx,d=c+1;
  if(tz[a]===BR||tz[b]===BR||tz[c]===BR||tz[d]===BR)continue;
  I.push(a,b,d,a,d,c);}
 const g=new THREE.BufferGeometry();
 g.setAttribute('position',new THREE.BufferAttribute(P,3));
 g.setAttribute('color',new THREE.BufferAttribute(C,3)); g.setIndex(I);
 const siatka=new THREE.Mesh(g,new THREE.MeshBasicMaterial({vertexColors:true,
  transparent:true,opacity:0.55,side:THREE.DoubleSide,depthWrite:false}));
 scena.add(siatka);
 const bT=document.getElementById('teren'); bT.style.display='';
 bT.onclick=()=>{siatka.visible=!siatka.visible;bT.classList.toggle('wl',siatka.visible);};}
// ścieżka skanera (trajektoria) - żółta linia i animacja przejazdu
let klatka=null;
if(D.sciezka&&D.sciezka.length>1){
 const S=D.sciezka, L=S.length;
 const g=new THREE.BufferGeometry();
 g.setAttribute('position',new THREE.BufferAttribute(new Float32Array(S.flat()),3));
 const lin=new THREE.Line(g,new THREE.LineBasicMaterial({color:0xffd34d}));
 scena.add(lin);
 const bS=document.getElementById('sciezka'); bS.style.display='';
 bS.onclick=()=>{lin.visible=!lin.visible;bS.classList.toggle('wl',lin.visible);};
 if(D.odkryj){
  document.getElementById('przejazd').style.display='';
  const znak=new THREE.Mesh(new THREE.SphereGeometry(0.45,16,12),
   new THREE.MeshBasicMaterial({color:0xff5a36}));
  const okP=[];for(let i=0;i<=72;i++){const a=i/72*Math.PI*2;
   okP.push(Math.cos(a)*D.zasieg,Math.sin(a)*D.zasieg,0);}
  const okG=new THREE.BufferGeometry();
  okG.setAttribute('position',new THREE.BufferAttribute(new Float32Array(okP),3));
  const okrag=new THREE.Line(okG,new THREE.LineBasicMaterial({color:0xff5a36,
   transparent:true,opacity:0.7}));
  znak.visible=okrag.visible=false; scena.add(znak); scena.add(okrag);
  const bO=document.getElementById('odtworz'), bC=document.getElementById('calosc'),
   bF=document.getElementById('sledz'), su=document.getElementById('suwak'),
   te=document.getElementById('tempo'), inf=document.getElementById('przejazdInfo'),
   teO=document.getElementById('tempoOpis');
  let poz=L-1, gra=false, sledz=false, ost=0, met=0;
  const DY=D.dyst, dl=DY[L-1];
  function wsk(m){let a=0,b=L-1;while(a<b){const c=(a+b)>>1;if(DY[c]<m)a=c+1;else b=c;}return a;}
  function opisTempa(){teO.textContent='Prędkość przejazdu: '+te.value+' m/s';}
  te.oninput=opisTempa; opisTempa();
  function caly(){gra=false;bO.textContent='▶ Odtwórz przejazd';poz=L-1;
   geo.setDrawRange(0,Infinity);lin.geometry.setDrawRange(0,Infinity);
   znak.visible=okrag.visible=false;su.value=1000;inf.textContent='';}
  function ustaw(k,anim){poz=Math.max(0,Math.min(L-1,k));const i=Math.floor(poz),p=S[i];
   if(!anim)met=DY[i];
   geo.setDrawRange(0,D.odkryj[i]);lin.geometry.setDrawRange(0,i+1);
   if(sledz){v3.set(p[0]-znak.position.x,p[1]-znak.position.y,p[2]-znak.position.z);
    if(znak.visible){ster.target.add(v3);kam.position.add(v3);}}
   znak.position.set(p[0],p[1],p[2]);okrag.position.set(p[0],p[1],p[2]);
   znak.visible=okrag.visible=true;
   su.value=Math.round(poz/(L-1)*1000);
   inf.textContent=DY[i].toFixed(0)+' z '+dl.toFixed(0)+' m · '+
    D.odkryj[i].toLocaleString('pl')+' punktów';}
  bO.onclick=()=>{if(gra){gra=false;bO.textContent='▶ Odtwórz przejazd';return;}
   if(poz>=L-1)ustaw(0);gra=true;ost=performance.now();bO.textContent='❚❚ Pauza';};
  bC.onclick=caly;
  bF.onclick=()=>{sledz=!sledz;bF.classList.toggle('wl',sledz);
   if(sledz&&znak.visible){const d=ster.target.clone().sub(znak.position);
    ster.target.sub(d);kam.position.sub(d);}};
  su.oninput=()=>{const k=su.value/1000*(L-1);if(k>=L-1&&!gra){caly();return;}ustaw(k);};
  klatka=t=>{if(!gra)return;const dt=Math.min(0.1,(t-ost)/1000);ost=t;
   met+=dt*Number(te.value); ustaw(wsk(met),true);
   if(poz>=L-1){gra=false;bO.textContent='▶ Odtwórz przejazd';}};}}
// kliknięcie w drzewo
const ray=new THREE.Raycaster(), mysz=new THREE.Vector2(); let dol=null;
rend.domElement.addEventListener('pointerdown',e=>{dol=[e.clientX,e.clientY];});
rend.domElement.addEventListener('pointerup',e=>{
 if(!dol||Math.hypot(e.clientX-dol[0],e.clientY-dol[1])>4)return;
 mysz.set(e.clientX/innerWidth*2-1,-(e.clientY/innerHeight)*2+1);
 ray.setFromCamera(mysz,kam);
 ray.params.Points.threshold=kam.position.distanceTo(ster.target)/300;
 const h=ray.intersectObject(chmura);
 const t=h.find(x=>(drz[x.index]>0||kp(x.index))&&pos[x.index*3+2]>-1000);
 if(t&&kp(t.index)){if(!tylko){wybierz(null,false);pokazKrzew(krz[t.index]);}}
 else if(t)wybierz(drz[t.index],false); else if(!tylko)wybierz(null,false);});
addEventListener('resize',()=>{kam.aspect=innerWidth/innerHeight;
 kam.updateProjectionMatrix();rend.setSize(innerWidth,innerHeight);});
const v3=new THREE.Vector3(), prawo=new THREE.Vector3();
(function petla(t){requestAnimationFrame(petla);if(klatka&&t)klatka(t);
 ster.update();rend.render(scena,kam);
 if(numery)for(const e of NR.children){const d=D.drzewa[e.dataset.t];
  v3.set(d.x,d.y,(d.h||10)+0.5).project(kam);
  const wid=Number.isFinite(d.x)&&v3.z<1&&!(tylko&&wybrane!==Number(e.dataset.t))&&!(!krzewyWid&&d.k);
  e.style.display=wid?'block':'none';
  e.style.left=((v3.x+1)/2*innerWidth)+'px';e.style.top=((1-v3.y)/2*innerHeight)+'px';}
 if(pierT.visible){prawo.setFromMatrixColumn(kam.matrixWorld,0);
  v3.copy(pierT.position).addScaledVector(prawo,pierT.scale.x*1.1).project(kam);
  PL.style.visibility=v3.z<1?'visible':'hidden';
  PL.style.left=((v3.x+1)/2*innerWidth)+'px';PL.style.top=((1-v3.y)/2*innerHeight)+'px';}})();
// ---------------- sprawdzanie drzew po kolei ----------------
const KLUCZ='lts_spr_'+D.nazwa; let dec={};
try{dec=JSON.parse(localStorage.getItem(KLUCZ)||'{}');}catch(e){dec={};}
function zapiszLok(){try{localStorage.setItem(KLUCZ,JSON.stringify(dec));}catch(e){}}
function waga(t){const d=D.drzewa[t];
 if(d.kc==='krzew')return 0; if(d.kc==='złom')return 1; if(d.kc==='niepewny')return 2;
 if(d.u)return 3; if(d.d===null)return 4; return 5;}
const kolej=Object.keys(D.drzewa).map(Number).sort((a,b)=>waga(a)-waga(b)||a-b);
let poz=0, sprOn=false;
const SPR=document.getElementById('spr');
function opisDec(t){const x=dec[t]; if(!x)return D.drzewa[t].s?'sprawdzone wcześniej':'';
 return 'Twoja decyzja: '+[x.d==='drzewo'?'drzewo OK':x.d==='krzew'?'krzak':x.d==='złom'?'złom':'',
  x.g?('gatunek '+x.g):''].filter(Boolean).join(', ');}
function pokazSpr(){const t=kolej[poz],d=D.drzewa[t];
 document.getElementById('sprTyt').textContent='Drzewo '+t;
 const zr=Object.keys(dec).length;
 document.getElementById('sprLic').textContent=(poz+1)+' z '+kolej.length+
  ' · decyzji: '+zr+' · najpierw drzewa podejrzane';
 const f=(v,n,j)=>v===null||v===undefined?'–':v.toLocaleString('pl',{minimumFractionDigits:n,maximumFractionDigits:n})+' '+j;
 document.getElementById('sprDane').innerHTML=
  (d.g||'–')+' · pierśnica '+f(d.d,1,'cm')+' · wysokość '+f(d.h,1,'m')+
  (d.kc&&d.kc!=='ok'?'<br><b style="color:#e0b070">program: '+(d.kc==='krzew'?'krzak':d.kc)+'</b>':'')+
  (d.u?'<br><span style="color:#8a9691">'+d.u+'</span>':'');
 const im=document.getElementById('sprImg');
 if(d.img){im.src=d.img;im.style.display='block';}else im.style.display='none';
 document.getElementById('sprDec').textContent=opisDec(t);
 tylko=false; wybierz(t,true);}
function decyduj(pole,w){const t=kolej[poz]; dec[t]=Object.assign(dec[t]||{},{[pole]:w});
 zapiszLok(); if(pole==='d'&&w==='krzew'){delete dec[t].g;}
 if(poz<kolej.length-1)poz++; pokazSpr();}
document.querySelectorAll('[data-d]').forEach(b=>b.onclick=()=>decyduj('d',b.dataset.d));
document.querySelectorAll('[data-g]').forEach(b=>b.onclick=()=>{const t=kolej[poz];
 dec[t]=Object.assign(dec[t]||{},{g:b.dataset.g,d:(dec[t]&&dec[t].d)||'drzewo'});zapiszLok();
 if(poz<kolej.length-1)poz++;pokazSpr();});
document.getElementById('sprPomin').onclick=()=>{if(poz<kolej.length-1)poz++;pokazSpr();};
document.getElementById('sprWstecz').onclick=()=>{if(poz>0)poz--;pokazSpr();};
document.getElementById('sprStart').onclick=()=>{sprOn=true;SPR.style.display='block';
 document.getElementById('info').style.display='none';
 tryb='drzewo';pokazSpr();};
document.getElementById('sprKoniec').onclick=()=>{sprOn=false;SPR.style.display='none';
 wybierz(null,false);};
document.getElementById('sprImg').onclick=()=>{document.getElementById('duzyImg').src=
 document.getElementById('sprImg').src;document.getElementById('duzy').style.display='flex';};
document.getElementById('duzy').onclick=()=>{document.getElementById('duzy').style.display='none';};
document.getElementById('sprZapisz').onclick=async()=>{
 const wiersze=['nr;decyzja;gatunek'];
 Object.keys(dec).map(Number).sort((a,b)=>a-b).forEach(t=>{
  wiersze.push(t+';'+(dec[t].d||'')+';'+(dec[t].g||''));});
 const tekst='\ufeff'+wiersze.join('\r\n')+'\r\n', nazwa=D.nazwa+'_sprawdzenie.csv';
 try{ if(window.showSaveFilePicker){
   const h=await showSaveFilePicker({suggestedName:nazwa,
     types:[{description:'CSV',accept:{'text/csv':['.csv']}}]});
   const w=await h.createWritable(); await w.write(tekst); await w.close();
   document.getElementById('sprDec').textContent='Zapisano '+nazwa+'.'; return;}
 }catch(e){ if(e.name==='AbortError')return; }
 const a=document.createElement('a');
 a.href=URL.createObjectURL(new Blob([tekst],{type:'text/csv'}));
 a.download=nazwa; a.click();
 document.getElementById('sprDec').textContent='Plik '+nazwa+' jest w Pobranych - przenieś go do 01_RAPORT.';};
addEventListener('keydown',e=>{if(!sprOn||e.target.tagName==='SELECT')return;
 const m={'1':()=>decyduj('d','drzewo'),'2':()=>decyduj('d','krzew'),'3':()=>decyduj('d','złom'),
  '4':()=>document.querySelector('[data-g="świerk"]').click(),
  '5':()=>document.querySelector('[data-g="buk"]').click(),
  'ArrowRight':()=>document.getElementById('sprPomin').click(),' ':()=>document.getElementById('sprPomin').click(),
  'ArrowLeft':()=>document.getElementById('sprWstecz').click()};
 if(m[e.key]){e.preventDefault();m[e.key]();}});
if(location.hash==='#sprawdzanie')document.getElementById('sprStart').click();
koloruj();
</script></body></html>"""


# wersja angielska szablonu: pary (tekst polski, angielski); wartości
# decyzji w pliku z wersji angielskiej: tree / shrub / snag, spruce / beech
ZAMIANY_EN = [
    ('<html lang="pl">', '<html lang="en">'),
    ('<div class="grupa">Kolor</div>', '<div class="grupa">Colour</div>'),
    ('class="wl">drzewa</button>', 'class="wl">trees</button>'),
    ('>pień / gałęzie / liście</button>', '>stem / branches / leaves</button>'),
    ('>wysokość</button></div>', '>height</button></div>'),
    ('<div class="grupa">Drzewo</div>', '<div class="grupa">Tree</div>'),
    ('– wybierz drzewo –', '– choose a tree –'),
    ('>Tylko to drzewo<', '>Only this tree<'),
    ('>Wszystkie<', '>All<'),
    ('Wielkość punktów', 'Point size'),
    ('>Numery drzew<', '>Tree numbers<'),
    ('>Ścieżka skanera<', '>Scanner path<'),
    ('>Teren<', '>Terrain<'),
    ('<div class="grupa">Przejazd skanera</div>',
     '<div class="grupa">Scanner walk-through</div>'),
    ('▶ Odtwórz przejazd', '▶ Play walk-through'),
    ('❚❚ Pauza', '❚❚ Pause'),
    ('>Cała chmura<', '>Whole cloud<'),
    ('>Kamera za skanerem<', '>Camera follows scanner<'),
    ("'Prędkość przejazdu: '", "'Walking speed: '"),
    ("+' z '+dl.toFixed(0)+' m · '", "+' of '+dl.toFixed(0)+' m · '"),
    ("D.odkryj[i].toLocaleString('pl')+' punktów'",
     "D.odkryj[i].toLocaleString('en')+' points'"),
    ('class="wl">Krzewy widoczne</button>', 'class="wl">Shrubs visible</button>'),
    ("'Krzewy widoczne':'Krzewy ukryte'", "'Shrubs visible':'Shrubs hidden'"),
    ('>Widok od nowa<', '>Reset view<'),
    ('<div class="grupa">Sprawdzanie</div>', '<div class="grupa">Review</div>'),
    ('>Sprawdź drzewa po kolei<', '>Review trees one by one<'),
    ('alt="obrazek drzewa"', 'alt="tree image"'),
    ('data-d="drzewo">1 · Drzewo OK<', 'data-d="tree">1 · Tree OK<'),
    ('data-d="krzew">2 · Krzak<', 'data-d="shrub">2 · Shrub<'),
    ('data-d="złom">3 · Złom<', 'data-d="snag">3 · Snag<'),
    ('data-g="świerk">4 · Świerk<', 'data-g="spruce">4 · Spruce<'),
    ('data-g="buk">5 · Buk<', 'data-g="beech">5 · Beech<'),
    ('→ · Pomiń', '→ · Skip'),
    ('← Wstecz', '← Back'),
    ('>Zapisz sprawdzenie<', '>Save review<'),
    ('>Zakończ<', '>Finish<'),
    ('Zapisz plik w folderze wyników skanu,\n w 01_RAPORT, i przelicz raport '
     '(w oknie @@PROG@@ przycisk „Przelicz raport”).',
     'Save the file in the scan results folder,\n in 01_RAPORT, and '
     'recalculate the report (button “Recalculate report” in the @@PROG@@ '
     'window).'),
    ('lewy przycisk – obrót · prawy – przesuwanie ·\nkółko – przybliżenie · '
     'kliknij drzewo, żeby zobaczyć dane', 'left button – rotate · right – '
     'pan ·\nwheel – zoom · click a tree to see its data'),
    ("' drzew · '", "' trees · '"),
    ("+' punktów'", "+' points'"),
    ("toLocaleString('pl'", "toLocaleString('en'"),
    ("</span>pień'+", "</span>stem'+"),
    ("</span>gałęzie<span", "</span>branches<span"),
    ("</span>ulistnienie'+", "</span>foliage'+"),
    ("</span>podszyt';", "</span>understory';"),
    ("innerHTML='nisko <span", "innerHTML='low <span"),
    ("</span> wysoko ('", "</span> high ('"),
    ("'każde drzewo ma swój kolor<br>", "'each tree has its own colour<br>"),
    ("</span>krzew (pominięty w wynikach)'",
     "</span>shrub (excluded from results)'"),
    ("'<h2>Drzewo '", "'<h2>Tree '"),
    ('<td>Gatunek</td>', '<td>Species</td>'),
    ('<td>skąd</td>', '<td>source</td>'),
    ('<td>Pierśnica</td>', '<td>DBH</td>'),
    ('<td>Wysokość</td>', '<td>Height</td>'),
    ('<td>Miąższość grubizny</td>', '<td>Merch. volume ≥7 cm</td>'),
    ('Prawdopodobnie krzew – pominięty w wynikach.',
     'Probably a shrub – excluded from results.'),
    ("o.textContent='Drzewo '+t+(d.g&&d.g!=='nieokreślony'?",
     "o.textContent='Tree '+t+(d.g&&d.g!=='unspecified'?"),
    ("(d.k?' · krzew':'')", "(d.k?' · shrub':'')"),
    ("'sprawdzone wcześniej'", "'reviewed earlier'"),
    ("'Twoja decyzja: '+[x.d==='drzewo'?'drzewo OK':x.d==='krzew'?'krzak':"
     "x.d==='złom'?'złom':'',\n  x.g?('gatunek '+x.g):'']",
     "'Your decision: '+[x.d==='tree'||x.d==='drzewo'?'tree OK':"
     "x.d==='shrub'||x.d==='krzew'?'shrub':x.d==='snag'||x.d==='złom'?"
     "'snag':'',\n  x.g?('species '+x.g):'']"),
    ("textContent='Drzewo '+t;", "textContent='Tree '+t;"),
    ("+' z '+kolej.length+\n  ' · decyzji: '+zr+' · najpierw drzewa "
     "podejrzane'", "+' of '+kolej.length+\n  ' · decisions: '+zr+' · "
     "suspicious trees first'"),
    ("' · pierśnica '+f(d.d,1,'cm')+' · wysokość '",
     "' · DBH '+f(d.d,1,'cm')+' · height '"),
    ("program: '+(d.kc==='krzew'?'krzak':d.kc)",
     "program: '+({krzew:'shrub',złom:'snag',niepewny:'uncertain'}[d.kc]"
     "||d.kc)"),
    ("if(pole==='d'&&w==='krzew')", "if(pole==='d'&&w==='shrub')"),
    ("d:(dec[t]&&dec[t].d)||'drzewo'", "d:(dec[t]&&dec[t].d)||'tree'"),
    ("['nr;decyzja;gatunek']", "['nr;decision;species']"),
    ("D.nazwa+'_sprawdzenie.csv'", "D.nazwa+'_review.csv'"),
    ("'Zapisano '+nazwa+'.'", "'Saved '+nazwa+'.'"),
    ("'Plik '+nazwa+' jest w Pobranych - przenieś go do 01_RAPORT.'",
     "'The file '+nazwa+' is in Downloads - move it to 01_RAPORT.'"),
    ("'1':()=>decyduj('d','drzewo'),'2':()=>decyduj('d','krzew'),"
     "'3':()=>decyduj('d','złom'),", "'1':()=>decyduj('d','tree'),"
     "'2':()=>decyduj('d','shrub'),'3':()=>decyduj('d','snag'),"),
    ('[data-g="świerk"]', '[data-g="spruce"]'),
    ('[data-g="buk"]', '[data-g="beech"]'),
    ("location.hash==='#sprawdzanie'", "location.hash==='#review'"),
    ('>Pierśnica na pniu<', '>DBH on the stem<'),
    ("' krzewów · '", "' shrubs · '"),
    ("krzewy 0,3–4 m (podszyt)'", "shrubs 0.3–4 m (understory)'"),
    ("'<h2>Krzew '", "'<h2>Shrub '"),
    ("<td>Pole z góry</td>", "<td>Area from above</td>"),
    ("Krzew nie wchodzi do drzew ani miąższości.",
     "A shrub is not counted as a tree or in the volume."),
    ("PL.innerHTML='pierśnica <b>'", "PL.innerHTML='DBH <b>'"),
    ("<small>1,3 m nad gruntem</small>", "<small>1.3 m above ground</small>"),
]


def przetlumacz(szablon):
    for pl_, en_ in ZAMIANY_EN:
        assert pl_ in szablon, pl_          # szablon zmieniony - popraw parę
        szablon = szablon.replace(pl_, en_)
    return szablon


if __name__ == "__main__":
    main()
