"""
LidarTreeSegmenter - ścieżka skanera (trajektoria) z pliku obok skanu.

Skaner ręczny albo plecakowy (SLAM) zapisuje, którędy szedł operator.
Ścieżka mówi, z których stron było widać każde drzewo i jak daleko od
skanera stało, a pokazana na mapie i w widoku 3D tłumaczy, czemu niektóre
pnie są widoczne tylko z jednej strony.

Skąd program bierze ścieżkę (pierwsze, co znajdzie):
  1. plik wybrany w oknie LidarTreeSegmenter (zapisany w ustawieniach skanu),
  2. wyniki\\<skan>\\01_RAPORT\\<skan>_sciezka.* (albo inny plik ze słowem
     traj / trajectory / sciezka / path / odom / pose w nazwie),
  3. folder skanu: plik ze słowem traj... i nazwą skanu, np. do
     _N0h__r25.laz pasuje _N0h_Trajectory.las.

Formaty:
  .las .laz           punkty ścieżki (czas z gps_time, jeśli jest)
  .txt .csv .xyz .pts tekst: kolumny z nagłówkiem (time, x, y, z ...) albo
                      bez (x y z, czas x y z jak TUM, 12 liczb jak KITTI);
                      separator przecinek, średnik, tabulator albo spacja;
                      linie z # % // na początku są pomijane
  .ply                ascii albo binarny, wierzchołki x y z (i czas)
Ścieżka musi być w tym samym układzie współrzędnych co skan.
"""

import re
import struct
from pathlib import Path

import numpy as np

import lts_jezyk as J
import lts_uklad as U

SLOWA = ("traj", "sciezka", "ścieżka", "path", "odom", "pose", "track")
ROZSZERZENIA = (".las", ".laz", ".txt", ".csv", ".xyz", ".pts", ".asc",
                ".ply")
ZASIEG_WIDOCZNOSCI_M = 15.0   # skąd liczy się, że drzewo było widać
SEKTORY = 36                  # obejście drzewa liczone w sektorach po 10°
DALEKO_M = 12.0               # drzewo dalej od ścieżki - pomiar mniej pewny

NAZWY_CZASU = {"time", "timestamp", "t", "gps_time", "gpstime", "sec",
               "seconds", "time_s", "utc", "stamp", "header.stamp",
               "field.header.stamp", "czas"}
NAZWY_OSI = {
    "x": {"x", "px", "tx", "pos_x", "posx", "position_x", "x_m", "easting",
          "e", "east", "pose.position.x", "field.pose.pose.position.x"},
    "y": {"y", "py", "ty", "pos_y", "posy", "position_y", "y_m", "northing",
          "n", "north", "pose.position.y", "field.pose.pose.position.y"},
    "z": {"z", "pz", "tz", "pos_z", "posz", "position_z", "z_m", "height",
          "h", "elevation", "alt", "pose.position.z",
          "field.pose.pose.position.z"},
}


# ----------------------------------------------------------------------
# szukanie pliku
# ----------------------------------------------------------------------
def rdzen(nazwa):
    """_N0h__r25 -> n0h (bez przycięcia _r25, _segmenty i podkreśleń)."""
    n = Path(nazwa).stem.lower().replace("_segmenty", "")
    n = re.sub(r"_+r\d+$", "", n)
    return n.strip("_ ")


def _pasuje(p):
    n = p.name.lower()
    return p.is_file() and p.suffix.lower() in ROZSZERZENIA and \
        any(s in n for s in SLOWA)


def kandydaci(folder, nazwa):
    """Pliki ścieżki w folderze; najpierw te z nazwą skanu."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    r = rdzen(nazwa)
    pl = [p for p in folder.iterdir() if _pasuje(p)]
    z_nazwa = [p for p in pl if r and r in p.name.lower()]
    if z_nazwa:
        return sorted(z_nazwa, key=lambda p: len(p.name))
    return pl if len(pl) == 1 else []


def znajdz(kat, nazwa, plik_skanu=None):
    """Ścieżka do pliku trajektorii albo None."""
    import lts_ustawienia as UST
    wyb = UST.wczytaj(kat, nazwa).get("sciezka")
    if wyb:
        if Path(wyb).is_file():
            return Path(wyb)
        print(J.t(f"         UWAGA: wybranej ścieżki skanera nie ma: {wyb}",
                  f"         WARNING: the chosen scanner path is missing: "
                  f"{wyb}"), flush=True)
    rap = Path(kat) / U.RAPORT
    wlasne = sorted(rap.glob(f"{nazwa}_sciezka.*")) + \
        sorted(rap.glob(f"{nazwa}_path.*")) if rap.is_dir() else []
    for p in wlasne:
        if p.suffix.lower() in ROZSZERZENIA:
            return p
    k = kandydaci(rap, nazwa)
    if k:
        return k[0]
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
        for folder in (p.parent, p.parent.parent):
            k = kandydaci(folder, p.stem)
            if k:
                return k[0]
    return None


# ----------------------------------------------------------------------
# wczytywanie
# ----------------------------------------------------------------------
def _las(plik):
    import laspy
    las = laspy.read(str(plik))
    xyz = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                           np.asarray(las.z)])
    t = None
    if "gps_time" in las.point_format.dimension_names:
        t = np.asarray(las.gps_time, float)
        if np.ptp(t) == 0:
            t = None
    return xyz, t


def _ply(plik):
    dane = Path(plik).read_bytes()
    kon = dane.find(b"end_header")
    if not dane.startswith(b"ply") or kon < 0:
        raise ValueError(J.t("to nie jest plik PLY", "not a PLY file"))
    nagl = dane[:kon].decode("ascii", "replace").splitlines()
    start = kon + len(b"end_header")
    start += 2 if dane[start:start + 2] == b"\r\n" else 1
    fmt = next(l.split()[1] for l in nagl if l.startswith("format"))
    TYPY = {"char": "b", "int8": "b", "uchar": "B", "uint8": "B",
            "short": "h", "int16": "h", "ushort": "H", "uint16": "H",
            "int": "i", "int32": "i", "uint": "I", "uint32": "I",
            "float": "f", "float32": "f", "double": "d", "float64": "d"}
    elementy, biez = [], None
    for l in nagl:
        s = l.split()
        if s[:1] == ["element"]:
            biez = [s[1], int(s[2]), []]
            elementy.append(biez)
        elif s[:1] == ["property"] and biez is not None:
            if s[1] == "list":
                raise ValueError(J.t("PLY z listami (siatka) - potrzebne same "
                                     "punkty", "PLY with lists (a mesh) - "
                                     "points only are needed"))
            biez[2].append((s[-1].lower(), TYPY[s[1]]))
    if elementy[0][0] != "vertex":
        raise ValueError(J.t("w PLY nie ma wierzchołków", "no vertices in "
                             "the PLY"))
    _, n, wl = elementy[0]
    nazwy = [w[0] for w in wl]
    if fmt == "ascii":
        tekst = dane[start:].decode("ascii", "replace").split()
        a = np.array(tekst[:n * len(wl)], float).reshape(n, len(wl))
    else:
        zn = "<" if fmt == "binary_little_endian" else ">"
        dt = np.dtype([(nm, zn + ty) for nm, ty in wl])
        a = np.frombuffer(dane, dt, count=n, offset=start)
        a = np.column_stack([a[nm].astype(float) for nm in nazwy])
    kol = {nm: i for i, nm in enumerate(nazwy)}
    xyz = a[:, [kol["x"], kol["y"], kol["z"]]]
    tn = next((nm for nm in nazwy if nm in NAZWY_CZASU), None)
    return xyz, (a[:, kol[tn]] if tn else None)


def _liczby(linia, sep):
    s = linia.strip().split(sep) if sep else linia.split()
    out = []
    for x in s:
        x = x.strip().strip('"')
        if sep in (";", "\t") or sep is None:
            x = x.replace(",", ".") if x.count(",") == 1 and "." not in x \
                else x
        out.append(x)
    return out


def _tekst(plik):
    raw = Path(plik).read_bytes()
    for kod in ("utf-8-sig", "cp1250", "latin-1"):
        try:
            tekst = raw.decode(kod)
            break
        except UnicodeDecodeError:
            continue
    linie = [l for l in tekst.splitlines() if l.strip()]
    naglowek = None
    dane = []
    for l in linie:
        s = l.strip()
        if s.startswith(("#", "//", ";", "'")) or (s.startswith("%") and
                                                     dane):
            # komentarz; ostatni komentarz przed danymi może być nagłówkiem
            if not dane:
                naglowek = s.lstrip("#/;%' ")
            continue
        dane.append(s)
    if not dane:
        raise ValueError(J.t("plik jest pusty", "the file is empty"))
    pierwsza = dane[0]
    sep = next((c for c in (";", "\t", ",") if c in pierwsza), None)
    if re.search(r"[A-Za-z_]{2,}|^[xyzXYZt]\b", pierwsza.lstrip("%")):
        naglowek = pierwsza.lstrip("%# ")
        dane = dane[1:]
    wiersze = []
    for l in dane:
        try:
            wiersze.append([float(x) for x in _liczby(l, sep)])
        except ValueError:
            continue
    if not wiersze:
        raise ValueError(J.t("nie znalazłem liczb", "no numbers found"))
    k = min(len(w) for w in wiersze)
    a = np.array([w[:k] for w in wiersze], float)

    if naglowek:
        nazwy = [x.strip().strip('"').lower()
                 for x in (naglowek.split(sep) if sep else naglowek.split())]
        nazwy = nazwy[:k]
        def kolumna(zbior, koncowka=None):
            for i, nm in enumerate(nazwy):
                if nm in zbior or (koncowka and nm.endswith(koncowka)):
                    return i
            return None
        ix, iy, iz = (kolumna(NAZWY_OSI[o], f".{o}") for o in "xyz")
        it = kolumna(NAZWY_CZASU, "time")
        if None not in (ix, iy, iz):
            return a[:, [ix, iy, iz]], (a[:, it] if it is not None else None)
    # bez nagłówka - zgadujemy po liczbie kolumn
    if k == 12:                                    # KITTI: macierz 3x4
        return a[:, [3, 7, 11]], None
    if k >= 4 and np.all(np.diff(a[:, 0]) >= 0) and np.ptp(a[:, 0]) > 0:
        return a[:, 1:4], a[:, 0]                  # czas x y z (np. TUM)
    if k >= 3:
        return a[:, 0:3], None
    raise ValueError(J.t("za mało kolumn (potrzebne x y z)",
                         "too few columns (x y z needed)"))


def wczytaj(plik):
    """dict: xyz (N,3), czas (N,) albo None, plik, dlugosc_m."""
    plik = Path(plik)
    r = plik.suffix.lower()
    if r in (".las", ".laz"):
        xyz, czas = _las(plik)
    elif r == ".ply":
        xyz, czas = _ply(plik)
    else:
        xyz, czas = _tekst(plik)
    ok = np.isfinite(xyz).all(1)
    xyz = xyz[ok]
    czas = czas[ok] if czas is not None else None
    if czas is not None:
        kol = np.argsort(czas, kind="stable")
        xyz, czas = xyz[kol], czas[kol]
    if len(xyz) < 2:
        raise ValueError(J.t("ścieżka ma mniej niż 2 punkty",
                             "the path has fewer than 2 points"))
    return {"xyz": xyz, "czas": czas, "plik": plik,
            "dlugosc_m": float(np.hypot(*np.diff(xyz[:, :2], axis=0).T)
                               .sum())}


def pokrywa_sie(xyz, xy_skanu, zapas=30.0):
    """Czy ścieżka leży tam, gdzie skan (ten sam układ współrzędnych)."""
    lo, hi = np.nanmin(xy_skanu, 0) - zapas, np.nanmax(xy_skanu, 0) + zapas
    w = ((xyz[:, :2] >= lo) & (xyz[:, :2] <= hi)).all(1)
    return w.mean() > 0.5


def uprosc(xyz, krok=0.25):
    """Co ok. krok metrów - do rysowania."""
    zost = [0]
    for i in range(1, len(xyz)):
        if np.linalg.norm(xyz[i] - xyz[zost[-1]]) >= krok:
            zost.append(i)
    if zost[-1] != len(xyz) - 1:
        zost.append(len(xyz) - 1)
    return xyz[zost]


# ----------------------------------------------------------------------
# widoczność drzew ze ścieżki
# ----------------------------------------------------------------------
def widocznosc(xy_drzew, xyz_sciezki, zasieg=ZASIEG_WIDOCZNOSCI_M):
    """Dla każdego drzewa: odległość od ścieżki [m], obejście [%] (jaka
    część z 36 sektorów po 10° wokół pnia ma punkt ścieżki w zasięgu)
    i maska widzianych sektorów (N, 36)."""
    from scipy.spatial import cKDTree
    xy = np.asarray(xy_drzew, float)
    s = uprosc(xyz_sciezki, 0.1)[:, :2]
    drz = cKDTree(s)
    odl, _ = drz.query(np.nan_to_num(xy, nan=1e9))
    sekt = np.zeros((len(xy), SEKTORY), bool)
    for i, idx in enumerate(drz.query_ball_point(np.nan_to_num(xy, nan=1e9),
                                                 zasieg)):
        if idx:
            d = s[idx] - xy[i]
            kat = np.degrees(np.arctan2(d[:, 1], d[:, 0])) % 360
            sekt[i, (kat // (360 / SEKTORY)).astype(int)] = True
    odl = np.where(np.isfinite(xy).all(1), odl, np.nan)
    return odl, sekt.mean(1) * 100, sekt


def dla_skanu(kat, nazwa, plik_skanu=None, xy_skanu=None, cicho=False):
    """Znajdź i wczytaj ścieżkę skanu; None, gdy jej nie ma albo nie pasuje.
    Błędy tylko wypisuje - bez ścieżki reszta działa jak dawniej."""
    p = znajdz(kat, nazwa, plik_skanu)
    if p is None:
        return None
    try:
        s = wczytaj(p)
    except Exception as e:                         # noqa: BLE001
        print(J.t(f"         UWAGA: nie umiem odczytać ścieżki skanera "
                  f"{p.name}: {e}",
                  f"         WARNING: cannot read the scanner path "
                  f"{p.name}: {e}"), flush=True)
        return None
    if xy_skanu is not None and len(xy_skanu) and \
            not pokrywa_sie(s["xyz"], xy_skanu):
        print(J.t(f"         UWAGA: ścieżka {p.name} nie leży na skanie "
                  f"(inny układ współrzędnych?) - pomijam ją",
                  f"         WARNING: the path {p.name} does not lie on the "
                  f"scan (different coordinate system?) - skipping it"),
              flush=True)
        return None
    if not cicho:
        print(J.t(f"         ścieżka skanera: {p.name}, {len(s['xyz']):,} "
                  f"punktów, {s['dlugosc_m']:.0f} m",
                  f"         scanner path: {p.name}, {len(s['xyz']):,} "
                  f"points, {s['dlugosc_m']:.0f} m"), flush=True)
    return s
