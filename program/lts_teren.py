"""
LidarTreeSegmenter - dopasowanie skanu do drzew zmierzonych w terenie
=========================================================

Kilka drzew (zwykle 5, ze środka powierzchni) ma pozycję z GPS (Garmin)
i pierśnicę zmierzoną średnicomierzem. Skan ma współrzędne lokalne
skanera, bez kierunku północy. Ten moduł szuka obrotu i przesunięcia,
które nakładają drzewa ze skanu na drzewa z terenu, i dzięki temu:

  - wyniki dostają prawdziwe współrzędne (GeoPackage do QGIS),
  - raport porównuje pierśnice i wysokości z terenu ze skanem.

Dopasowanie liczy jednocześnie odległość i pierśnicę, bo GPS pod okapem
myli się o kilka metrów, a pierśnica jest pewna. Szukamy po wszystkich
parach drzew (teren) i parach drzew (skan) o zgodnej odległości
i pierśnicy, każdą parę sprawdzamy na wszystkich drzewach, najlepszą
poprawiamy metodą najmniejszych kwadratów (obrót + przesunięcie, bez
skalowania - skaner mierzy odległości dokładnie).

PLIK Z POMIAREM: <skan>_pomiar.csv (albo .xlsx), szablon w
LidarTreeSegmenter\\SZABLON_pomiar.csv. Kolumny:
  nr            numer drzewa w terenie
  szerokosc     szerokość geograficzna, np. 42.123456 albo N42 07.407
  dlugosc       długość geograficzna, np. 23.456789 albo E023 27.407
  piersnica_cm  pierśnica [cm]
  gatunek       (opcjonalnie) np. świerk, buk
  wysokosc_m    (opcjonalnie)
Zamiast szerokosc/dlugosc można podać X, Y i EPSG (np. 2180).
Pozycje mogą też być w pliku .gpx z Garmina (punkt nazwany numerem
drzewa), a pierśnice w <skan>_pomiar.csv bez współrzędnych.
"""

import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd

import lts_jezyk as J

SIGMA_GPS = 5.0          # typowy błąd Garmina pod okapem [m]
SIGMA_D = 4.0            # dopuszczalna różnica pierśnic teren - skan [cm]
MAX_ODL = 12.0           # dalej niż tyle od pozycji GPS - to nie to drzewo [m]
KARA = 9.0               # koszt drzewa bez pary (w jednostkach sigma^2)

# ----------------------------------------------------------------------
# odwzorowanie poprzeczne Merkatora (UTM, PUWG 1992) bez pyproj
# ----------------------------------------------------------------------
A_WGS = 6378137.0
F_WGS = 1 / 298.257223563


def _tm_stale():
    n = F_WGS / (2 - F_WGS)
    A = A_WGS / (1 + n) * (1 + n ** 2 / 4 + n ** 4 / 64)
    al = [n / 2 - 2 * n ** 2 / 3 + 5 * n ** 3 / 16,
          13 * n ** 2 / 48 - 3 * n ** 3 / 5,
          61 * n ** 3 / 240]
    return n, A, al


def tm(lat, lon, lon0, k0, fe, fn):
    """Szerokość/długość WGS84 [stopnie] -> E, N [m] (szereg Krügera)."""
    n, A, al = _tm_stale()
    fi = np.radians(np.asarray(lat, float))
    dl = np.radians(np.asarray(lon, float) - lon0)
    e = 2 * math.sqrt(n) / (1 + n)
    t = np.sinh(np.arctanh(np.sin(fi)) - e * np.arctanh(e * np.sin(fi)))
    xi = np.arctan2(t, np.cos(dl))
    eta = np.arctanh(np.sin(dl) / np.sqrt(1 + t ** 2))
    E = eta + sum(al[j] * np.cos(2 * (j + 1) * xi) * np.sinh(2 * (j + 1) * eta)
                  for j in range(3))
    N = xi + sum(al[j] * np.sin(2 * (j + 1) * xi) * np.cosh(2 * (j + 1) * eta)
                 for j in range(3))
    return fe + k0 * A * E, fn + k0 * A * N


def uklad_dla(lon, lat, epsg=None):
    """Parametry odwzorowania: PUWG 1992 (2180) albo strefa UTM."""
    if epsg == 2180:
        return {"epsg": 2180, "lon0": 19.0, "k0": 0.9993, "fe": 500000.0,
                "fn": -5300000.0, "nazwa": "ETRS89 / Poland CS92"}
    if epsg and 32601 <= epsg <= 32660:
        strefa = epsg - 32600
    else:
        strefa = int((lon + 180) // 6) + 1
    pn = lat >= 0
    return {"epsg": (32600 if pn else 32700) + strefa,
            "lon0": -183 + 6 * strefa, "k0": 0.9996, "fe": 500000.0,
            "fn": 0.0 if pn else 10000000.0,
            "nazwa": f"WGS 84 / UTM zone {strefa}{'N' if pn else 'S'}"}


def wkt(u):
    geo = ('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,'
           '298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",'
           '0.0174532925199433]]')
    if u["epsg"] == 2180:
        geo = ('GEOGCS["ETRS89",DATUM["European_Terrestrial_Reference_'
               'System_1989",SPHEROID["GRS 1980",6378137,298.257222101]],'
               'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]')
    return (f'PROJCS["{u["nazwa"]}",{geo},PROJECTION["Transverse_Mercator"],'
            f'PARAMETER["latitude_of_origin",0],'
            f'PARAMETER["central_meridian",{u["lon0"]:g}],'
            f'PARAMETER["scale_factor",{u["k0"]:g}],'
            f'PARAMETER["false_easting",{u["fe"]:g}],'
            f'PARAMETER["false_northing",{u["fn"]:g}],UNIT["metre",1],'
            f'AUTHORITY["EPSG","{u["epsg"]}"]]')


# ----------------------------------------------------------------------
# wczytanie pomiaru
# ----------------------------------------------------------------------
def stopnie(s):
    """'42.123456', '42,123456', 'N42 07.407', '42°07'24.4\"' -> stopnie."""
    if s is None or (isinstance(s, float) and not math.isfinite(s)):
        return np.nan
    if isinstance(s, (int, float, np.floating)):
        return float(s)
    t = str(s).strip().upper().replace(",", ".")
    if not t:
        return np.nan
    znak = -1 if t[0] in "SW" or t.endswith(("S", "W")) or t.startswith("-") \
        else 1
    liczby = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]
    if not liczby:
        return np.nan
    w = liczby[0]
    if len(liczby) > 1:
        w += liczby[1] / 60
    if len(liczby) > 2:
        w += liczby[2] / 3600
    return znak * w


def _bez_ogonkow(t):
    import unicodedata
    t = str(t).lower().replace("ł", "l")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", t)


def _kolumna(df, *nazwy):
    m = {_bez_ogonkow(c): c for c in df.columns}
    for n in nazwy:
        k = _bez_ogonkow(n)
        if k in m:
            return m[k]
    return None


def _czytaj_tabele(p):
    if p.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(p, dtype=str)
    try:
        tekst = p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:             # CSV zapisany w polskim Excelu
        tekst = p.read_text(encoding="cp1250", errors="replace")
    linie = [l for l in tekst.splitlines() if l.strip() and
             not l.lstrip().startswith("#")]
    sep = ";" if linie and linie[0].count(";") >= linie[0].count(",") \
        else ","
    from io import StringIO
    return pd.read_csv(StringIO("\n".join(linie)), sep=sep, dtype=str)


def _liczba(s):
    try:
        return float(str(s).replace(",", ".").strip())
    except (TypeError, ValueError):
        return np.nan


def czytaj_gpx(p):
    root = ET.parse(p).getroot()
    wynik = {}
    for wpt in root.iter():
        if wpt.tag.endswith("wpt"):
            nazwa = next((c.text for c in wpt if c.tag.endswith("name")), "")
            nr = re.findall(r"\d+", nazwa or "")
            if nr:
                wynik[int(nr[0])] = (float(wpt.get("lat")),
                                     float(wpt.get("lon")))
    return wynik


def znajdz_pomiar(kat, nazwa, plik_skanu=None):
    miejsca = [kat / "01_RAPORT", kat]
    if plik_skanu:
        miejsca.append(Path(plik_skanu).parent)
    for m in miejsca:
        for kon in ("_pomiar", "_field"):      # wersja angielska: _field
            for roz in (".csv", ".xlsx", ".gpx"):
                p = m / f"{nazwa}{kon}{roz}"
                if p.exists():
                    return p
    return None


def wczytaj_pomiar(p, epsg=None):
    """DataFrame: nr, x, y (metry w układzie wynikowym), d_cm, gatunek,
    h_m; oraz słownik układu."""
    p = Path(p)
    gpx = {}
    if p.suffix.lower() == ".gpx":
        gpx = czytaj_gpx(p)
        csv = next((q for q in (p.with_suffix(".csv"), p.with_suffix(".xlsx"))
                    if q.exists()), None)
        df = _czytaj_tabele(csv) if csv else pd.DataFrame(
            {"nr": list(gpx)})
    else:
        df = _czytaj_tabele(p)
        g = next((q for q in (p.with_suffix(".gpx"),) if q.exists()), None)
        if g:
            gpx = czytaj_gpx(g)
    k_nr = _kolumna(df, "nr", "numer", "drzewo", "id")
    k_lat = _kolumna(df, "szerokosc", "lat", "latitude", "szer")
    k_lon = _kolumna(df, "dlugosc", "lon", "longitude", "dl", "lng")
    k_x = _kolumna(df, "x", "e", "easting")
    k_y = _kolumna(df, "y", "n", "northing")
    k_ep = _kolumna(df, "epsg", "uklad")
    k_d = _kolumna(df, "piersnica_cm", "piersnica", "dbh", "dbh_cm", "d13")
    k_g = _kolumna(df, "gatunek", "gat", "species")
    k_h = _kolumna(df, "wysokosc_m", "wysokosc", "h", "height", "height_m")
    if k_nr is None:
        raise ValueError(J.t("w pliku pomiaru brak kolumny nr",
                           "the field measurement file has no column nr"))
    nr = pd.to_numeric(df[k_nr], errors="coerce")
    df = df[nr.notna()].copy()
    nr = nr[nr.notna()].astype(int).to_numpy()
    lat = df[k_lat].map(stopnie).to_numpy(float) if k_lat else \
        np.full(len(df), np.nan)
    lon = df[k_lon].map(stopnie).to_numpy(float) if k_lon else \
        np.full(len(df), np.nan)
    for i, n in enumerate(nr):
        if (not np.isfinite(lat[i])) and n in gpx:
            lat[i], lon[i] = gpx[n]
    d = df[k_d].map(_liczba).to_numpy(float) if k_d else \
        np.full(len(df), np.nan)
    out = pd.DataFrame({"nr": nr, "d_cm": d,
                        "gatunek": df[k_g].fillna("").str.strip().to_numpy()
                        if k_g else "",
                        "h_m": df[k_h].map(_liczba).to_numpy(float)
                        if k_h else np.nan})
    if np.isfinite(lat).sum() >= 2:
        ok = np.isfinite(lat)
        u = uklad_dla(np.nanmean(lon[ok]), np.nanmean(lat[ok]), epsg)
        x, y = tm(lat, lon, u["lon0"], u["k0"], u["fe"], u["fn"])
        out["x"], out["y"] = x, y
        out["lat"], out["lon"] = lat, lon
    elif k_x and k_y:
        out["x"] = df[k_x].map(_liczba).to_numpy(float)
        out["y"] = df[k_y].map(_liczba).to_numpy(float)
        ep = int(_liczba(df[k_ep].dropna().iloc[0])) if k_ep and \
            df[k_ep].notna().any() else epsg
        if not ep:
            raise ValueError(J.t("współrzędne X/Y bez kolumny EPSG",
                               "X/Y coordinates without an EPSG column"))
        u = {"epsg": ep, "nazwa": f"EPSG:{ep}"}
    else:
        raise ValueError(J.t("w pliku pomiaru brak współrzędnych "
                           "(szerokosc/dlugosc albo X/Y + EPSG albo plik "
                           ".gpx)", "the field measurement file has no "
                           "coordinates (lat/lon, or X/Y + EPSG, or a .gpx "
                           "file)"))
    out = out[np.isfinite(out.x) & np.isfinite(out.y)].reset_index(drop=True)
    return out, u


# ----------------------------------------------------------------------
# dopasowanie
# ----------------------------------------------------------------------
def kabsch(P, Q, w=None):
    """Obrót R i przesunięcie t: Q ~ R @ P + t (2D, bez skali)."""
    w = np.ones(len(P)) if w is None else np.asarray(w, float)
    cp = (P * w[:, None]).sum(0) / w.sum()
    cq = (Q * w[:, None]).sum(0) / w.sum()
    H = ((P - cp) * w[:, None]).T @ (Q - cq)
    U_, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U_.T))
    R = Vt.T @ np.diag([1, d]) @ U_.T
    return R, cq - R @ cp


def _ocena(R, t, P, dP, S, dS):
    """Koszt dopasowania: pozycja + pierśnica, każde drzewo terenowe
    z jednym drzewem skanu (zachłannie od najpewniejszych)."""
    Pt = P @ R.T + t
    D = np.hypot(Pt[:, None, 0] - S[None, :, 0], Pt[:, None, 1] - S[None, :, 1])
    dd = np.abs(dP[:, None] - dS[None, :])
    dd = np.where(np.isfinite(dd), dd, 2 * SIGMA_D)
    C = (D / SIGMA_GPS) ** 2 + (dd / SIGMA_D) ** 2
    C[D > MAX_ODL] = np.inf
    pary, koszt = {}, 0.0
    uzyte = set()
    for i in np.argsort(C.min(1)):
        j_ = [j for j in np.argsort(C[i]) if j not in uzyte]
        if j_ and C[i, j_[0]] < KARA:
            pary[i] = j_[0]
            uzyte.add(j_[0])
            koszt += C[i, j_[0]]
        else:
            koszt += KARA
    return koszt, pary


def dopasuj(teren, skan):
    """teren: DataFrame x, y, d_cm (układ wynikowy); skan: nr, x, y, d_cm
    (lokalny). Zwraca słownik z obrotem, przesunięciem i parami."""
    P = teren[["x", "y"]].to_numpy(float)
    dP = teren.d_cm.to_numpy(float)
    S = skan[["x", "y"]].to_numpy(float)
    dS = skan.d_cm.to_numpy(float)
    n, m = len(P), len(S)
    if n < 2 or m < 2:
        raise ValueError(J.t("za mało drzew do dopasowania (potrzeba co "
                           "najmniej 2 z pomiarem i 2 w skanie)",
                           "too few trees to match (at least 2 measured "
                           "and 2 in the scan are needed)"))
    # kandydaci: drzewa skanu o zgodnej pierśnicy
    zgodne = [np.flatnonzero(~np.isfinite(dS) | ~np.isfinite(dP[i]) |
                             (np.abs(dS - dP[i]) <= max(2.5 * SIGMA_D,
                                                        0.25 * dP[i])))
              for i in range(n)]
    najlepsze = []
    for i in range(n):
        for k in range(i + 1, n):
            dik = np.hypot(*(P[k] - P[i]))
            for a in zgodne[i]:
                for b in zgodne[k]:
                    if a == b:
                        continue
                    dab = np.hypot(*(S[b] - S[a]))
                    if abs(dab - dik) > 2.5 * SIGMA_GPS:
                        continue
                    # obrót tak, by kierunek (a->b) w skanie = (i->k) teren
                    kat = (math.atan2(*(P[k] - P[i])[::-1])
                           - math.atan2(*(S[b] - S[a])[::-1]))
                    R = np.array([[math.cos(kat), -math.sin(kat)],
                                  [math.sin(kat), math.cos(kat)]])
                    # przekształcenie skan -> teren: P ~ R S + t
                    sr_t = (P[i] + P[k]) / 2
                    sr_s = (S[a] + S[b]) / 2
                    t = sr_t - R @ sr_s
                    # oceniamy w kierunku teren -> skan
                    Ri = R.T
                    ti = -Ri @ t
                    koszt, pary = _ocena(Ri, ti, P, dP, S, dS)
                    najlepsze.append((koszt, kat, pary))
    if not najlepsze:
        raise ValueError(J.t("nie znalazłem drzew skanu o pierśnicach i "
                           "odległościach zgodnych z pomiarem",
                           "no scan trees with DBH and distances matching "
                           "the field measurement were found"))
    najlepsze.sort(key=lambda z: z[0])

    def popraw(pary):
        """Najmniejsze kwadraty na parach, ponowne parowanie, 3 razy."""
        R, t = np.eye(2), np.zeros(2)
        koszt = np.inf
        for _ in range(3):
            if len(pary) < 2:
                break
            ii = np.array(list(pary))
            jj = np.array([pary[i] for i in ii])
            R, t = kabsch(S[jj], P[ii])         # teren ~ R skan + t
            koszt, pary = _ocena(R.T, -R.T @ t, P, dP, S, dS)
        return koszt, pary, R, t

    # poprawiamy kilkadziesiąt najlepszych hipotez i wybieramy po poprawce
    wyniki = []
    for z in najlepsze[:60]:
        koszt, pary, R, t = popraw(z[2])
        if len(pary) >= 2:
            wyniki.append((koszt, pary, R, t))
    if not wyniki:
        raise ValueError(J.t("nie udało się dopasować drzew",
                           "the trees could not be matched"))
    wyniki.sort(key=lambda z: z[0])
    koszt, pary, R, t = wyniki[0]
    obrot = math.degrees(math.atan2(R[1, 0], R[0, 0]))

    def kat_r(R_):
        return math.degrees(math.atan2(R_[1, 0], R_[0, 0]))
    drugie = next((z for z in wyniki[1:]
                   if abs((kat_r(z[2]) - obrot + 180) % 360 - 180) > 25),
                  None)
    ii = np.array(list(pary))
    jj = np.array([pary[i] for i in ii])
    res = np.hypot(*((S[jj] @ R.T + t) - P[ii]).T) if len(ii) else np.array([])
    return {"R": R, "t": t, "obrot_deg": obrot, "pary": dict(zip(ii.tolist(),
                                                             jj.tolist())),
            "koszt": koszt, "koszt_drugi": None if drugie is None
            else drugie[0], "reszty_m": res}


def przeksztalc(xy, R, t):
    xy = np.asarray(xy, float)
    return xy @ R.T + t


def ocena_slowna(wyn, n_teren):
    n = len(wyn["pary"])
    sr = float(np.sqrt(np.mean(wyn["reszty_m"] ** 2))) if n else np.nan
    dr = wyn["koszt_drugi"]
    if n < 3:
        return J.t("słabe", "weak"), J.t(
            f"dopasowano tylko {n} z {n_teren} drzew - kierunek może być "
            f"błędny, sprawdź w QGIS", f"only {n} of {n_teren} trees "
            f"matched - the orientation may be wrong, check in QGIS")
    if dr is not None and dr < wyn["koszt"] + 3:
        return J.t("niepewne", "uncertain"), J.t(
            "jest drugie, inaczej obrócone ustawienie prawie tak samo "
            "dobre - sprawdź w QGIS", "another, differently rotated "
            "solution is almost as good - check in QGIS")
    if sr > 2 * SIGMA_GPS:
        return J.t("niepewne", "uncertain"), J.t(
            f"duże odchyłki (średnio {sr:.1f} m)",
            f"large offsets (mean {sr:.1f} m)")
    return J.t("dobre", "good"), J.t(
        f"dopasowano {n} z {n_teren} drzew, średnia odchyłka {sr:.1f} m "
        f"(to głównie błąd GPS)", f"{n} of {n_teren} trees matched, mean "
        f"offset {sr:.1f} m (mostly GPS error)")


def zapisz_json(p, wyn, u, teren, skan, ocena):
    d = {"epsg": u["epsg"], "uklad": u.get("nazwa"),
         "obrot_deg": round(wyn["obrot_deg"], 2),
         "R": np.round(wyn["R"], 8).tolist(),
         "t": np.round(wyn["t"], 3).tolist(),
         "ocena": ocena[0], "opis": ocena[1],
         "pary": [{"teren": int(teren.nr[i]), "skan": int(skan.nr[j])}
                  for i, j in wyn["pary"].items()]}
    Path(p).write_text(json.dumps(d, ensure_ascii=False, indent=1),
                       encoding="utf-8")
    return d
