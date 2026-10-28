"""
LidarTreeSegmenter - zapis do GeoPackage (.gpkg)
===================================

GeoPackage to jeden plik z wieloma warstwami, który otwiera QGIS, ArcGIS
i każdy inny GIS. Ten moduł zapisuje go samym Pythonem (sqlite3), bez
geopandas, żeby nie trzeba było nic doinstalowywać.

Warstwy (wszystkie w jednym pliku 01_RAPORT\\<skan>.gpkg):
  drzewa          punkt w miejscu pnia na 1,3 m, wszystkie dane drzewa
                  (po raporcie także pierśnica, miąższość, grupa gatunkowa)
  przekroj_1_3m   okrąg pnia na 1,3 m (poligon), średnica, pokrycie, punkty
  przekroj_3m     to samo na 3 m
  punkty_1_3m     punkty chmury w plastrze 1,3 m ±5 cm (z numerem drzewa)
  punkty_3m       punkty chmury w plastrze 3 m ±5 cm
  krzewy          obrysy krzewów 0,3-4 m (dopisuje raport)
(osi pni, gałęzi i koron już nie zapisujemy - patrz ZBEDNE)

Współrzędne są takie jak w skanie. Jeśli skan ma układ współrzędnych
(np. EPSG:2180), plik go dostaje. Jeśli nie, układ jest „nieokreślony”
i w QGIS warstwy leżą we współrzędnych lokalnych skanera.
"""

import datetime as dt
import json
import math
import sqlite3
import struct
from pathlib import Path

import numpy as np
import pandas as pd

import lts_jezyk as J

TYPY = {"POINT": 1, "LINESTRING": 2, "POLYGON": 3}

# wersja angielska: nazwy warstw i pól po angielsku (tłumaczy zapisz_warstwe,
# programy podają nazwy polskie)
WARSTWY_EN = {"drzewa": "trees", "pnie_osie": "stem_axes",
              "przekroj_1_3m": "section_1_3m", "przekroj_3m": "section_3m",
              "punkty_1_3m": "points_1_3m", "punkty_3m": "points_3m",
              "galezie": "branches", "korony": "crowns",
              "pomiar_terenowy": "field_measurement",
              "odchylki_gps": "gps_offsets",
              "sciezka_skanera": "scanner_path",
              "etykiety_skanera": "scanner_labels",
              "teren_wysokosc": "terrain_elevation",
              "teren_spadek": "terrain_slope",
              "teren_cieniowanie": "terrain_hillshade",
              "warstwice": "contours", "krzewy": "shrubs"}
WARSTWY_PL = {v: k for k, v in WARSTWY_EN.items()}
POLA_EN = {
    "liczba_punktow": "point_count", "wysokosc_drzewa_m": "tree_height_m",
    "pien_okregow": "stem_circles", "pien_od_m": "stem_from_m",
    "pien_do_m": "stem_to_m", "dorysowano_od_m": "reconstructed_from_m",
    "dorysowano_do_m": "reconstructed_to_m", "srednica_13_m": "dbh_lts_m",
    "srednica_13_zrodlo": "dbh_lts_source",
    "srednica_u_gory_m": "diameter_top_m", "pozycja_x": "position_x",
    "pozycja_y": "position_y", "gatunek": "species",
    "grupa_gatunkowa": "species_group",
    "grupa_pewnosc_proc": "group_confidence_pct",
    "podstawa_korony_m": "crown_base_m", "dl_korony_proc": "crown_length_pct",
    "wnetrze_13": "interior_share_1_3m", "wnetrze_3m": "interior_share_3m",
    "kontrola_pnia": "stem_check", "srednica_13_pewna": "dbh_reliable",
    "kontrola_powod": "check_reason", "proc_nic": "pct_none",
    "proc_pien": "pct_stem", "proc_galezie": "pct_branches",
    "proc_ulistnienie": "pct_foliage", "proc_podszyt": "pct_understory",
    "od_m": "from_m", "do_m": "to_m", "okregow": "circles",
    "dorysowanych": "reconstructed", "wysokosc_m": "height_m",
    "srednica_cm": "diameter_cm", "pokrycie_deg": "coverage_deg",
    "punktow": "points", "zrodlo": "source",
    "punkty_w_srodku": "interior_share", "czesc": "part",
    "pole_m2": "area_m2", "wysokosc_max_m": "max_height_m", "promien_m": "radius_m",
    "piersnica_cm": "dbh_cm", "uwagi": "notes",
    "smuklosc_h_d": "slenderness_h_d", "pole_przekroju_m2": "basal_area_m2",
    "miazszosc_grubizny_m3": "volume_merch_m3",
    "gatunek_zrodlo": "species_source",
    "gatunek_pewnosc_proc": "group_confidence_pct",
    "wykryte_od_gory": "detected_from_above",
    "piersnica_lts_cm": "dbh_lts_cm",
    "piersnica_lts_zrodlo": "dbh_lts_source",
    "miazszosc_strzaly_zmierzonej_m3": "volume_measured_stem_m3",
    "krzew": "shrub", "sprawdzone": "reviewed", "nr_teren": "nr_field",
    "nr_skan": "nr_scan", "gat_teren": "species_field",
    "gat_skan": "species_scan", "d_teren": "dbh_field_cm",
    "d_skan": "dbh_scan_cm", "h_teren": "height_field_m",
    "h_skan": "height_scan_m", "odl": "distance_m",
    "d_roz": "dbh_diff_cm", "h_roz": "height_diff_m",
    "dopasowanie": "match_quality", "odleglosc_m": "distance_m",
    "odl_od_sciezki_m": "distance_from_path_m",
    "obejscie_ze_sciezki_proc": "path_coverage_pct", "plik": "file",
    "dlugosc_m": "length_m",
    "glowna": "index_contour",
    "kod": "code", "nr_drzewa": "tree_nr", "przypisana": "assigned",
    "czas": "time",
    "odl_od_okregu_cm": "dist_from_circle_cm",
}


# ----------------------------------------------------------------------
# geometria -> GeoPackage binary (nagłówek GP + WKB)
# ----------------------------------------------------------------------
def _wkb(typ, wsp, z):
    kod = TYPY[typ] + (1000 if z else 0)
    f = "<ddd" if z else "<dd"
    if typ == "POINT":
        return struct.pack("<BI", 1, kod) + struct.pack(f, *wsp)
    if typ == "LINESTRING":
        return (struct.pack("<BII", 1, kod, len(wsp))
                + b"".join(struct.pack(f, *p) for p in wsp))
    # POLYGON: jeden pierścień, zamknięty
    pier = list(wsp)
    if tuple(pier[0]) != tuple(pier[-1]):
        pier.append(pier[0])
    return (struct.pack("<BIII", 1, kod, 1, len(pier))
            + b"".join(struct.pack(f, *p) for p in pier))


def _gpkg(typ, wsp, z, srs):
    a = np.asarray(wsp, float).reshape(-1, 3 if z else 2)
    if typ == "POINT":
        naglowek = b"GP" + struct.pack("<BBi", 0, 0b00000001, srs)
    else:
        naglowek = (b"GP" + struct.pack("<BBi", 0, 0b00000011, srs)
                    + struct.pack("<dddd", a[:, 0].min(), a[:, 0].max(),
                                  a[:, 1].min(), a[:, 1].max()))
    return naglowek + _wkb(typ, a.tolist() if typ != "POINT" else a[0], z), a


def okrag(x, y, r, n=48):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.column_stack([x + r * np.cos(t), y + r * np.sin(t)])


def otoczka(xy):
    """Otoczka wypukła w rzucie z góry."""
    p = np.unique(np.round(np.asarray(xy, float), 2), axis=0)
    if len(p) < 3:
        return None
    try:
        from scipy.spatial import ConvexHull
        return p[ConvexHull(p).vertices]
    except Exception:                                    # noqa: BLE001
        pass                   # bez scipy (albo punkty w linii): ręcznie
    p = p[np.lexsort((p[:, 1], p[:, 0]))]

    def pol(pts):
        h = []
        for q in pts:
            while len(h) >= 2 and ((h[-1][0] - h[-2][0]) * (q[1] - h[-2][1])
                                   - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0])
                                   ) <= 0:
                h.pop()
            h.append(tuple(q))
        return h
    d, g = pol(p), pol(p[::-1])
    h = np.array(d[:-1] + g[:-1])
    return h if len(h) >= 3 else None


# ----------------------------------------------------------------------
# plik
# ----------------------------------------------------------------------
# skan bez układu współrzędnych: zamiast „układu nieokreślonego” (-1), który
# QGIS traktuje jak stopnie (zła skala, nie działa widoczność od skali),
# lokalny układ inżynierski w metrach
LOKALNY_ID = 990001
LOKALNY_WKT = ('LOCAL_CS["LidarTreeSegmenter - lokalny uklad skanu (metry)",'
               'LOCAL_DATUM["skan",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],'
               'AXIS["X",EAST],AXIS["Y",NORTH]]')


def id_ukladu(srs):
    """srs_id do zapisu w GeoPackage."""
    return srs[0] if srs[0] > 0 else LOKALNY_ID


def napraw_uklad(plik):
    """Pliki ze starszych wersji: warstwy w układzie -1 przepina na lokalny
    układ w metrach. Zwraca liczbę poprawionych warstw."""
    con = _otworz(plik, (-1, "undefined"))
    try:
        tab = [r[0] for r in con.execute(
            "SELECT table_name FROM gpkg_contents WHERE srs_id IN (-1, 0)")]
        if not tab:
            return 0
        nowy = struct.pack("<i", LOKALNY_ID)
        for t in tab:
            for k in ("gpkg_contents", "gpkg_geometry_columns",
                      "gpkg_tile_matrix_set"):
                try:
                    con.execute(f"UPDATE {k} SET srs_id=? WHERE table_name=? "
                                f"AND srs_id IN (-1, 0)", (LOKALNY_ID, t))
                except sqlite3.OperationalError:
                    pass
            kol = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
            if "geom" in kol:
                wier = con.execute(f'SELECT fid, geom FROM "{t}"').fetchall()
                con.executemany(f'UPDATE "{t}" SET geom=? WHERE fid=?',
                                [(g[:4] + nowy + g[8:], f) for f, g in wier
                                 if g])
        con.commit()
        return len(tab)
    finally:
        con.close()


def _otworz(plik, srs):
    nowy = not Path(plik).exists()
    con = sqlite3.connect(str(plik))
    if nowy:
        con.execute("PRAGMA application_id = 1196444487")   # 'GPKG'
        con.execute("PRAGMA user_version = 10200")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS gpkg_spatial_ref_sys (
      srs_name TEXT NOT NULL, srs_id INTEGER PRIMARY KEY,
      organization TEXT NOT NULL, organization_coordsys_id INTEGER NOT NULL,
      definition TEXT NOT NULL, description TEXT);
    CREATE TABLE IF NOT EXISTS gpkg_contents (
      table_name TEXT NOT NULL PRIMARY KEY, data_type TEXT NOT NULL,
      identifier TEXT UNIQUE, description TEXT DEFAULT '',
      last_change DATETIME NOT NULL DEFAULT
        (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
      min_x DOUBLE, min_y DOUBLE, max_x DOUBLE, max_y DOUBLE,
      srs_id INTEGER);
    CREATE TABLE IF NOT EXISTS gpkg_geometry_columns (
      table_name TEXT NOT NULL, column_name TEXT NOT NULL,
      geometry_type_name TEXT NOT NULL, srs_id INTEGER NOT NULL,
      z TINYINT NOT NULL, m TINYINT NOT NULL,
      CONSTRAINT pk_geom_cols PRIMARY KEY (table_name, column_name));
    """)
    wiersze = [
        ("Undefined cartesian SRS", -1, "NONE", -1, "undefined",
         J.t("układ nieokreślony", "undefined coordinate system")),
        ("Undefined geographic SRS", 0, "NONE", 0, "undefined",
         J.t("układ nieokreślony", "undefined coordinate system")),
        ("WGS 84 geodetic", 4326, "EPSG", 4326,
         'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,'
         '298.257223563]],PRIMEM["Greenwich",0],UNIT["degree",'
         '0.0174532925199433]]', "WGS 84"),
        ("LidarTreeSegmenter lokalny", LOKALNY_ID, "LTS", LOKALNY_ID, LOKALNY_WKT,
         J.t("lokalny układ skanera, metry (skan bez układu współrzędnych)",
             "local scanner system, metres (scan without a CRS)")),
    ]
    if srs[0] > 0 and srs[0] != 4326:
        wiersze.append((f"EPSG:{srs[0]}", srs[0], "EPSG", srs[0], srs[1],
                        J.t("układ skanu", "scan coordinate system")))
    con.executemany("INSERT OR IGNORE INTO gpkg_spatial_ref_sys VALUES "
                    "(?,?,?,?,?,?)", wiersze)
    return con


def _typ_kolumny(s):
    if pd.api.types.is_bool_dtype(s):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(s):
        return "INTEGER"
    if pd.api.types.is_float_dtype(s):
        return "REAL"
    return "TEXT"


def _wartosc(v):
    if v is None:
        return None
    if isinstance(v, (float, np.floating)):
        return None if not math.isfinite(v) else float(v)
    if isinstance(v, (np.bool_, bool)):
        return int(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, str):
        return v
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def zapisz_warstwe(plik, nazwa, typ, geometrie, atrybuty, z=False,
                   srs=(-1, "undefined"), opis=""):
    """Zapisuje (albo podmienia) jedną warstwę.

    geometrie - lista współrzędnych (punkt: (x, y[, z]); linia/poligon:
                tablica Nx2 albo Nx3); atrybuty - DataFrame o tej samej
                liczbie wierszy.
    """
    atrybuty = atrybuty.reset_index(drop=True)
    atrybuty.columns = [str(c) for c in atrybuty.columns]
    if J.EN:
        nazwa = WARSTWY_EN.get(nazwa, nazwa)
        atrybuty = J.wartosci(atrybuty, POLA_EN)
    inna = WARSTWY_PL.get(nazwa) if J.EN else WARSTWY_EN.get(nazwa)
    con = _otworz(plik, srs)
    try:
        for n_ in filter(None, (nazwa, inna)):   # też ta z drugiego języka
            con.execute(f'DROP TABLE IF EXISTS "{n_}"')
            con.execute("DELETE FROM gpkg_contents WHERE table_name=?",
                        (n_,))
            con.execute("DELETE FROM gpkg_geometry_columns WHERE "
                        "table_name=?", (n_,))
        kol = ", ".join(f'"{c}" {_typ_kolumny(atrybuty[c])}'
                        for c in atrybuty.columns if c.lower() != "fid")
        con.execute(f'CREATE TABLE "{nazwa}" (fid INTEGER PRIMARY KEY '
                    f'AUTOINCREMENT, geom {typ}{", " + kol if kol else ""})')
        nazwy = [c for c in atrybuty.columns if c.lower() != "fid"]
        zn = ", ".join(["?"] * (len(nazwy) + 1))
        lista = ", ".join(["geom"] + [f'"{c}"' for c in nazwy])
        mn = np.array([np.inf, np.inf]); mx = -mn
        wiersze = []
        rekordy = atrybuty[nazwy].astype(object).itertuples(index=False,
                                                             name=None)
        for g, rek in zip(geometrie, rekordy):
            blob, a = _gpkg(typ, g, z, id_ukladu(srs))
            mn = np.minimum(mn, a[:, :2].min(0))
            mx = np.maximum(mx, a[:, :2].max(0))
            wiersze.append([blob] + [_wartosc(v) for v in rek])
        con.executemany(f'INSERT INTO "{nazwa}" ({lista}) VALUES ({zn})',
                        wiersze)
        if not wiersze:
            mn = mx = np.array([0.0, 0.0])
        con.execute("INSERT INTO gpkg_contents (table_name, data_type, "
                    "identifier, description, last_change, min_x, min_y, "
                    "max_x, max_y, srs_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (nazwa, "features", nazwa, opis,
                     dt.datetime.now(dt.timezone.utc).strftime(
                         "%Y-%m-%dT%H:%M:%S.000Z"),
                     float(mn[0]), float(mn[1]), float(mx[0]), float(mx[1]),
                     id_ukladu(srs)))
        con.execute("INSERT INTO gpkg_geometry_columns VALUES (?,?,?,?,?,?)",
                    (nazwa, "geom", typ, id_ukladu(srs), 1 if z else 0, 0))
        con.commit()
    finally:
        con.close()
    return len(geometrie)


# warstwy ze starszych wersji, których już nie zapisujemy (za dużo warstw,
# nikt z nich nie korzystał) - raport usuwa je ze starych plików
ZBEDNE = ("pnie_osie", "galezie", "korony")


def usun_warstwy(plik, nazwy):
    """Usuwa warstwy (w obu językach) z GeoPackage. Zwraca usunięte."""
    if not Path(plik).exists():
        return []
    con = sqlite3.connect(str(plik))
    try:
        jest = {r[0] for r in con.execute(
            "SELECT table_name FROM gpkg_contents")}
        style = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                            "AND name='layer_styles'").fetchone()
        usun = [n_ for n in nazwy for n_ in (n, WARSTWY_EN.get(n))
                if n_ in jest]
        for n_ in usun:
            con.execute(f'DROP TABLE IF EXISTS "{n_}"')
            con.execute(f'DROP TABLE IF EXISTS "rtree_{n_}_geom"')  # QGIS
            for t_ in ("gpkg_contents", "gpkg_geometry_columns"):
                con.execute(f"DELETE FROM {t_} WHERE table_name=?", (n_,))
            if style:
                con.execute("DELETE FROM layer_styles WHERE f_table_name=?",
                            (n_,))
            if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                           "AND name='gpkg_extensions'").fetchone():
                con.execute("DELETE FROM gpkg_extensions WHERE table_name=?",
                            (n_,))
        con.commit()
        if usun:
            con.execute("VACUUM")
    finally:
        con.close()
    return usun


def uklad_skanu(las):
    """(srs_id, definicja WKT) z nagłówka LAS, albo układ nieokreślony."""
    try:
        crs = las.header.parse_crs()
        if crs is not None:
            epsg = crs.to_epsg()
            if epsg:
                return epsg, crs.to_wkt()
    except Exception:                                    # noqa: BLE001
        pass
    return -1, "undefined"


def zapisz_srs(plik_json, srs):
    Path(plik_json).write_text(json.dumps({"srs_id": srs[0], "wkt": srs[1]},
                                          ensure_ascii=False),
                               encoding="utf-8")


def wczytaj_srs(plik_json):
    try:
        d = json.loads(Path(plik_json).read_text(encoding="utf-8"))
        return int(d["srs_id"]), d["wkt"]
    except (OSError, ValueError, KeyError):
        return -1, "undefined"


# ----------------------------------------------------------------------
# kopia pliku w innym układzie (po dopasowaniu do pomiaru terenowego)
# ----------------------------------------------------------------------
def _czytaj_geom(blob):
    flagi = blob[3]
    env = (flagi >> 1) & 0b111
    poz = 8 + {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]
    wkb = blob[poz:]
    kod = struct.unpack("<I", wkb[1:5])[0]
    z = kod > 1000
    typ = {1: "POINT", 2: "LINESTRING", 3: "POLYGON"}[kod % 1000]
    w = 3 if z else 2
    if typ == "POINT":
        a = np.frombuffer(wkb[5:5 + 8 * w], "<f8").reshape(1, w)
    elif typ == "LINESTRING":
        n = struct.unpack("<I", wkb[5:9])[0]
        a = np.frombuffer(wkb[9:9 + 8 * w * n], "<f8").reshape(n, w)
    else:
        n = struct.unpack("<I", wkb[9:13])[0]
        a = np.frombuffer(wkb[13:13 + 8 * w * n], "<f8").reshape(n, w)
    return typ, z, a.copy()


# ----------------------------------------------------------------------
# przerzedzanie punktów plastra (żeby QGIS nie pokazywał plam punktów)
# ----------------------------------------------------------------------
SIATKA_PIEN_M = 0.01      # kora: jeden punkt na 1 cm - łuk pnia zostaje
SIATKA_RESZTA_M = 0.04    # gałęzie, liście, podszyt w plastrze: co 4 cm
NA_DRZEWO_MAX = 400       # warstwa gęstsza niż tyle na drzewo - przerzedź


def przerzedz_plaster(xy, czesci):
    """Indeksy punktów do zostawienia: jeden punkt na komórkę siatki,
    gęstszej dla kory (czesc "pien"), rzadszej dla reszty. Kształt łuku
    kory, z którego liczona jest pierśnica, zostaje; znika tylko
    nadmiar punktów leżących prawie w tym samym miejscu."""
    xy = np.asarray(xy, float)
    czesci = np.asarray(czesci).astype(str)
    zost = []
    for kora in (True, False):
        m = np.flatnonzero((czesci == "pien") == kora)
        if not len(m):
            continue
        k = SIATKA_PIEN_M if kora else SIATKA_RESZTA_M
        kom = np.floor(xy[m] / k).astype(np.int64)
        _, pierwszy = np.unique(kom, axis=0, return_index=True)
        zost.append(m[pierwszy])
    return np.sort(np.concatenate(zost)) if zost else np.zeros(0, int)


def przerzedz_warstwe_punktow(plik, nazwa, srs, opis=None):
    """Przerzedza istniejącą warstwę punktów plastra (pliki z wcześniejszych
    wersji, w których było do 3000 punktów na drzewo). Zwraca (przed, po)
    albo None, gdy nie trzeba."""
    import sqlite3
    con = sqlite3.connect(str(plik))
    try:
        if not con.execute("SELECT 1 FROM gpkg_contents WHERE table_name=?",
                           (nazwa,)).fetchone():
            return None
        kol = [r[1] for r in con.execute(f'PRAGMA table_info("{nazwa}")')]
        if "treeID" not in kol or "czesc" not in kol:
            return None
        n, nd = con.execute(f'SELECT COUNT(*), COUNT(DISTINCT treeID) FROM '
                            f'"{nazwa}"').fetchone()
        if not nd or n <= NA_DRZEWO_MAX * nd:
            return None
        inne = [k for k in kol if k not in ("fid", "geom")]
        wiersze = con.execute(
            f'SELECT geom, {", ".join(chr(34) + k + chr(34) for k in inne)} '
            f'FROM "{nazwa}" ORDER BY treeID').fetchall()
        opis = opis or (con.execute("SELECT description FROM gpkg_contents "
                                    "WHERE table_name=?", (nazwa,))
                        .fetchone() or [None])[0]
    finally:
        con.close()
    xyz = np.array([_czytaj_geom(w[0])[2][0] for w in wiersze])
    if xyz.shape[1] == 2:
        xyz = np.column_stack([xyz, np.zeros(len(xyz))])
    at = pd.DataFrame([w[1:] for w in wiersze], columns=inne)
    zost = []
    for _, grp in at.groupby("treeID", sort=False):
        i = grp.index.to_numpy()
        zost.append(i[przerzedz_plaster(xyz[i, :2], grp.czesc.to_numpy())])
    zost = np.sort(np.concatenate(zost))
    zapisz_warstwe(plik, nazwa, "POINT", xyz[zost],
                   at.iloc[zost].reset_index(drop=True), z=True, srs=srs,
                   opis=opis)
    con = sqlite3.connect(str(plik))
    con.execute("VACUUM")                    # plik robi się mniejszy
    con.close()
    return n, len(zost)


def przeksztalc_plik(we, wy, R, t, srs, dz=0.0):
    """Kopiuje wszystkie warstwy z we do wy, przeliczając współrzędne
    x, y -> R @ (x, y) + t (i z + dz) i nadając układ srs."""
    if Path(wy).exists():
        Path(wy).unlink()
    con = sqlite3.connect(str(we))
    try:
        warstwy = [r[0] for r in con.execute(
            "SELECT table_name FROM gpkg_contents WHERE data_type='features'")]
        for nazwa in warstwy:
            typ_w, z_w = con.execute(
                "SELECT geometry_type_name, z FROM gpkg_geometry_columns "
                "WHERE table_name=?", (nazwa,)).fetchone()
            opis = con.execute("SELECT description FROM gpkg_contents WHERE "
                               "table_name=?", (nazwa,)).fetchone()[0]
            kur = con.execute(f'SELECT * FROM "{nazwa}"')
            kol = [k[0] for k in kur.description]
            wiersze = kur.fetchall()
            ig = kol.index("geom")
            atr = pd.DataFrame([[w[i] for i in range(len(kol))
                                 if kol[i] not in ("geom", "fid")]
                                for w in wiersze],
                               columns=[k for k in kol
                                        if k not in ("geom", "fid")])
            typy = {r[1]: r[2] for r in
                    con.execute(f'PRAGMA table_info("{nazwa}")')}
            for k in atr.columns:            # zachowaj typy kolumn
                if typy.get(k) == "BOOLEAN":
                    atr[k] = atr[k].astype("boolean")
                elif typy.get(k) == "INTEGER":
                    atr[k] = pd.to_numeric(atr[k]).astype("Int64")
                elif typy.get(k) == "REAL":
                    atr[k] = pd.to_numeric(atr[k]).astype(float)
            geom = []
            for w in wiersze:
                _, z, a = _czytaj_geom(w[ig])
                a[:, :2] = a[:, :2] @ np.asarray(R).T + np.asarray(t)
                if z:
                    a[:, 2] += dz
                geom.append(a)
            zapisz_warstwe(wy, nazwa, typ_w, geom, atr, z=bool(z_w), srs=srs,
                           opis=opis)
    finally:
        con.close()
