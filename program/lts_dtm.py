"""
LidarTreeSegmenter - model terenu (DTM) z wysokości nad gruntem.

Krok 1 (tree_segmenter_tool) liczy model terenu i zapisuje przy każdym
punkcie wysokość nad gruntem (pole wys_nad_grunt). Wysokość gruntu pod
punktem to więc z - wys_nad_grunt. Z tego powstaje siatka terenu co 25 cm,
a z niej:
  - spadek [°] i ekspozycja (w którą stronę świata opada stok),
  - cieniowanie (teren oświetlony z północnego zachodu),
  - warstwice (poziomice),
  - statystyki do raportu (deniwelacja, średni spadek, ekspozycja).

Wszystko trafia do GeoPackage <skan>.gpkg:
  teren_wysokosc     raster z wysokością terenu [m] (2D gridded coverage -
                     QGIS pokazuje wartości i pozwala je stylizować)
  teren_spadek       raster ze spadkiem [°]
  teren_cieniowanie  obrazek: cieniowanie zabarwione wysokością
  warstwice          linie co 0,25 / 0,5 / 1 m (zależnie od deniwelacji)
Siatka zapisuje się też w 03_TABELE\\<skan>_teren.npz (dla raportu i 3D).
"""

import datetime as dt
import sqlite3
import struct
import zlib
from pathlib import Path

import numpy as np

import lts_jezyk as J

KROK_M = 0.25
TILE = 256
KIERUNKI = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
KIERUNKI_PL = ("północ", "północny wschód", "wschód", "południowy wschód",
               "południe", "południowy zachód", "zachód",
               "północny zachód")
KIERUNKI_EN = ("north", "north-east", "east", "south-east", "south",
               "south-west", "west", "north-west")


# ----------------------------------------------------------------------
# siatka
# ----------------------------------------------------------------------
def z_chmury(xyz, h, krok=KROK_M):
    """dict: x0, y0 (lewy dolny róg), krok, Z (ny, nx) z NaN poza skanem."""
    from scipy import ndimage
    zg = xyz[:, 2] - h
    ok = np.isfinite(zg)
    x0 = np.floor(xyz[ok, 0].min() / krok) * krok
    y0 = np.floor(xyz[ok, 1].min() / krok) * krok
    ix = ((xyz[ok, 0] - x0) / krok).astype(np.int64)
    iy = ((xyz[ok, 1] - y0) / krok).astype(np.int64)
    nx, ny = ix.max() + 1, iy.max() + 1
    k = iy * nx + ix
    # średnia z gruntu pod punktami komórki (grunt jest gładki, więc
    # średnia wystarcza i jest szybka)
    suma = np.bincount(k, zg[ok], minlength=nx * ny)
    ile = np.bincount(k, minlength=nx * ny)
    Z = np.full(nx * ny, np.nan)
    Z[ile > 0] = suma[ile > 0] / ile[ile > 0]
    Z = Z.reshape(ny, nx)
    # dziury do 1 m wypełnia najbliższa komórka
    puste = ~np.isfinite(Z)
    if puste.any():
        odl, (iy_, ix_) = ndimage.distance_transform_edt(
            puste, return_indices=True)
        bl = puste & (odl * krok <= 1.0)
        Z[bl] = Z[iy_[bl], ix_[bl]]
    return {"x0": float(x0), "y0": float(y0), "krok": float(krok), "Z": Z}


def zapisz(plik, dtm):
    np.savez_compressed(plik, x0=dtm["x0"], y0=dtm["y0"], krok=dtm["krok"],
                        Z=dtm["Z"].astype(np.float32))


def wczytaj(plik):
    if not Path(plik).exists():
        return None
    d = np.load(plik)
    return {"x0": float(d["x0"]), "y0": float(d["y0"]),
            "krok": float(d["krok"]), "Z": d["Z"].astype(float)}


def gladki(dtm, sigma_m=0.75):
    """Siatka wygładzona (bez schodków po interpolacji) - do spadku."""
    from scipy import ndimage
    Z = dtm["Z"]
    ok = np.isfinite(Z)
    s = sigma_m / dtm["krok"]
    licz = ndimage.gaussian_filter(np.where(ok, Z, 0.0), s)
    wag = ndimage.gaussian_filter(ok.astype(float), s)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(ok, licz / wag, np.nan)


def pochodne(dtm):
    """spadek [°] i ekspozycja [° od północy, zgodnie z zegarem]."""
    Z, k = gladki(dtm), dtm["krok"]
    dzdy, dzdx = np.gradient(Z, k)            # wiersze rosną na północ
    spadek = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    ekspozycja = (np.degrees(np.arctan2(-dzdx, -dzdy)) + 360) % 360
    return spadek, ekspozycja


def cieniowanie(dtm, azymut=315, wys=45):
    Z, k = gladki(dtm, 0.4), dtm["krok"]
    dzdy, dzdx = np.gradient(Z, k)
    nach = np.arctan(np.hypot(dzdx, dzdy))
    asp = np.arctan2(-dzdx, -dzdy)
    az, al = np.radians(azymut), np.radians(wys)
    c = np.sin(al) * np.cos(nach) + np.cos(al) * np.sin(nach) * \
        np.cos(az - asp)
    return np.clip(c, 0, 1)


def statystyki(dtm):
    Z = dtm["Z"]
    sp, ek = pochodne(dtm)
    ok = np.isfinite(Z) & np.isfinite(sp)
    if not ok.any():
        return None
    s = sp[ok]
    # ekspozycja przeważająca: średnia kierunkowa ważona spadkiem
    w = np.radians(ek[ok])
    kier = (np.degrees(np.arctan2((np.sin(w) * s).sum(),
                                  (np.cos(w) * s).sum())) + 360) % 360
    i = int(((kier + 22.5) % 360) // 45)
    return {"min": float(np.nanmin(Z)), "max": float(np.nanmax(Z)),
            "deniwelacja": float(np.nanmax(Z) - np.nanmin(Z)),
            "spadek_sr": float(s.mean()),
            "spadek_proc": float(np.tan(np.radians(s.mean())) * 100),
            "spadek_max": float(np.percentile(s, 95)),
            "ekspozycja_deg": float(kier), "ekspozycja": KIERUNKI[i],
            "ekspozycja_opis": (KIERUNKI_EN if J.EN else KIERUNKI_PL)[i]}


def interwal(dtm):
    r = np.nanmax(dtm["Z"]) - np.nanmin(dtm["Z"])
    return 0.25 if r < 3 else (0.5 if r < 10 else 1.0)


def warstwice(dtm, co=None):
    """[(wysokość, Nx3)] - linie terenu co `co` metrów."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    Z, k = dtm["Z"], dtm["krok"]
    co = co or interwal(dtm)
    lo, hi = np.nanmin(Z), np.nanmax(Z)
    poziomy = np.arange(np.ceil(lo / co) * co, hi + 1e-9, co)
    if len(poziomy) == 0:
        return []
    x = dtm["x0"] + (np.arange(Z.shape[1]) + 0.5) * k
    y = dtm["y0"] + (np.arange(Z.shape[0]) + 0.5) * k
    fig, ax = plt.subplots()
    cs = ax.contour(x, y, np.ma.masked_invalid(Z), levels=poziomy)
    wyn = []
    for poz, segs in zip(cs.levels, cs.allsegs):
        for s in segs:
            if len(s) >= 2:
                wyn.append((float(poz), np.column_stack(
                    [s, np.full(len(s), poz)])))
    plt.close(fig)
    return wyn


# ----------------------------------------------------------------------
# PNG bez dodatkowych bibliotek
# ----------------------------------------------------------------------
def _png(a, bity):
    """a: (h, w) szarość albo (h, w, 4) RGBA; bity 8 albo 16."""
    if a.ndim == 2:
        typ_kol, kan = 0, 1
    else:
        typ_kol, kan = 6, a.shape[2]
    h, w = a.shape[:2]
    if bity == 16:
        surowe = a.astype(">u2").reshape(h, w * kan).view(np.uint8)
    else:
        surowe = a.astype(np.uint8).reshape(h, w * kan)
    dane = b"".join(b"\x00" + surowe[i].tobytes() for i in range(h))

    def kaw(t, d):
        return (struct.pack(">I", len(d)) + t + d
                + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff))
    return (b"\x89PNG\r\n\x1a\n"
            + kaw(b"IHDR", struct.pack(">IIBBBBB", w, h, bity, typ_kol,
                                       0, 0, 0))
            + kaw(b"IDAT", zlib.compress(dane, 6)) + kaw(b"IEND", b""))


# ----------------------------------------------------------------------
# GeoPackage: rastry kafelkowe
# ----------------------------------------------------------------------
def _przygotuj(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS gpkg_tile_matrix_set (
      table_name TEXT NOT NULL PRIMARY KEY, srs_id INTEGER NOT NULL,
      min_x DOUBLE NOT NULL, min_y DOUBLE NOT NULL,
      max_x DOUBLE NOT NULL, max_y DOUBLE NOT NULL);
    CREATE TABLE IF NOT EXISTS gpkg_tile_matrix (
      table_name TEXT NOT NULL, zoom_level INTEGER NOT NULL,
      matrix_width INTEGER NOT NULL, matrix_height INTEGER NOT NULL,
      tile_width INTEGER NOT NULL, tile_height INTEGER NOT NULL,
      pixel_x_size DOUBLE NOT NULL, pixel_y_size DOUBLE NOT NULL,
      CONSTRAINT pk_ttm PRIMARY KEY (table_name, zoom_level));
    CREATE TABLE IF NOT EXISTS gpkg_extensions (
      table_name TEXT, column_name TEXT, extension_name TEXT NOT NULL,
      definition TEXT NOT NULL, scope TEXT NOT NULL,
      CONSTRAINT ge_tce UNIQUE (table_name, column_name, extension_name));
    CREATE TABLE IF NOT EXISTS gpkg_2d_gridded_coverage_ancillary (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      tile_matrix_set_name TEXT NOT NULL UNIQUE,
      datatype TEXT NOT NULL DEFAULT 'integer',
      scale REAL NOT NULL DEFAULT 1.0, offset REAL NOT NULL DEFAULT 0.0,
      precision REAL DEFAULT 1.0, data_null REAL,
      grid_cell_encoding TEXT DEFAULT 'grid-value-is-center',
      uom TEXT, field_name TEXT DEFAULT 'Height',
      quantity_definition TEXT DEFAULT 'Height');
    CREATE TABLE IF NOT EXISTS gpkg_2d_gridded_tile_ancillary (
      id INTEGER PRIMARY KEY AUTOINCREMENT, tpudt_name TEXT NOT NULL,
      tpudt_id INTEGER NOT NULL, scale REAL NOT NULL DEFAULT 1.0,
      offset REAL NOT NULL DEFAULT 0.0, min REAL DEFAULT NULL,
      max REAL DEFAULT NULL, mean REAL DEFAULT NULL,
      std_dev REAL DEFAULT NULL,
      UNIQUE (tpudt_name, tpudt_id));
    """)


def _usun(con, nazwa):
    con.execute(f'DROP TABLE IF EXISTS "{nazwa}"')
    for t, k in (("gpkg_contents", "table_name"),
                 ("gpkg_tile_matrix_set", "table_name"),
                 ("gpkg_tile_matrix", "table_name"),
                 ("gpkg_extensions", "table_name"),
                 ("gpkg_2d_gridded_coverage_ancillary",
                  "tile_matrix_set_name"),
                 ("gpkg_2d_gridded_tile_ancillary", "tpudt_name")):
        try:
            con.execute(f"DELETE FROM {t} WHERE {k}=?", (nazwa,))
        except sqlite3.OperationalError:
            pass


def _raster(con, nazwa, dtm, obraz, srs_id, opis, siatka=None):
    """obraz: (ny, nx) liczby (siatka = dict scale/offset/uom/pole)
    albo (ny, nx, 4) RGBA 8-bit. Wiersz 0 obrazu = północ."""
    k = dtm["krok"]
    ny, nx = obraz.shape[:2]
    mw, mh = -(-nx // TILE), -(-ny // TILE)
    x0, y1 = dtm["x0"], dtm["y0"] + ny * k
    x1, y0 = x0 + mw * TILE * k, y1 - mh * TILE * k
    _usun(con, nazwa)
    con.execute(f'CREATE TABLE "{nazwa}" (id INTEGER PRIMARY KEY '
                f'AUTOINCREMENT, zoom_level INTEGER NOT NULL, tile_column '
                f'INTEGER NOT NULL, tile_row INTEGER NOT NULL, tile_data '
                f'BLOB NOT NULL, UNIQUE (zoom_level, tile_column, tile_row))')
    teraz = dt.datetime.now(dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.000Z")
    con.execute("INSERT INTO gpkg_contents (table_name, data_type, "
                "identifier, description, last_change, min_x, min_y, max_x, "
                "max_y, srs_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (nazwa, "2d-gridded-coverage" if siatka else "tiles", nazwa,
                 opis, teraz, x0, dtm["y0"], x0 + nx * k, y1, srs_id))
    # zasięg danych w gpkg_contents, kafle (pełne 256 px) w tile_matrix_set
    con.execute("INSERT INTO gpkg_tile_matrix_set VALUES (?,?,?,?,?,?)",
                (nazwa, srs_id, x0, y0, x1, y1))
    con.execute("INSERT INTO gpkg_tile_matrix VALUES (?,?,?,?,?,?,?,?)",
                (nazwa, 0, mw, mh, TILE, TILE, k, k))
    if siatka:
        for tab, kol in (("gpkg_2d_gridded_coverage_ancillary", None),
                         ("gpkg_2d_gridded_tile_ancillary", None),
                         (nazwa, "tile_data")):
            con.execute("INSERT OR IGNORE INTO gpkg_extensions VALUES "
                        "(?,?,?,?,?)",
                        (tab, kol, "gpkg_2d_gridded_coverage",
                         "http://docs.opengeospatial.org/is/17-066r1/"
                         "17-066r1.html", "read-write"))
        con.execute("INSERT INTO gpkg_2d_gridded_coverage_ancillary "
                    "(tile_matrix_set_name, datatype, scale, offset, "
                    "precision, data_null, grid_cell_encoding, uom, "
                    "field_name, quantity_definition) VALUES "
                    "(?,?,?,?,?,?,?,?,?,?)",
                    (nazwa, "integer", siatka["scale"], siatka["offset"],
                     siatka["scale"], 65535, "grid-value-is-center",
                     siatka["uom"], siatka["pole"], siatka["pole"]))
    for r in range(mh):
        for c in range(mw):
            kaf = obraz[r * TILE:(r + 1) * TILE, c * TILE:(c + 1) * TILE]
            if siatka:
                pel = np.full((TILE, TILE), 65535, np.uint16)
                w = kaf
                ok = np.isfinite(w)
                if not ok.any():
                    continue
                v = np.round((w - siatka["offset"]) / siatka["scale"])
                pel[:w.shape[0], :w.shape[1]] = np.where(
                    ok, np.clip(v, 0, 65534), 65535).astype(np.uint16)
                blob = _png(pel, 16)
            else:
                pel = np.zeros((TILE, TILE, 4), np.uint8)
                pel[:kaf.shape[0], :kaf.shape[1]] = kaf
                if not pel[..., 3].any():
                    continue
                blob = _png(pel, 8)
            cur = con.execute(f'INSERT INTO "{nazwa}" (zoom_level, '
                              f'tile_column, tile_row, tile_data) VALUES '
                              f'(0,?,?,?)', (c, r, blob))
            if siatka:
                con.execute("INSERT INTO gpkg_2d_gridded_tile_ancillary "
                            "(tpudt_name, tpudt_id, scale, offset, min, max,"
                            " mean, std_dev) VALUES (?,?,1.0,0.0,?,?,?,?)",
                            (nazwa, cur.lastrowid, float(np.nanmin(kaf)),
                             float(np.nanmax(kaf)), float(np.nanmean(kaf)),
                             float(np.nanstd(kaf))))


def _kolory(Z, cien):
    """Cieniowanie zabarwione wysokością (zieleń nisko, brąz wysoko)."""
    ok = np.isfinite(Z)
    lo, hi = np.nanmin(Z), np.nanmax(Z)
    f = np.clip((Z - lo) / max(hi - lo, 1e-6), 0, 1)
    paleta = np.array([[86, 140, 76], [170, 178, 98], [196, 160, 98],
                       [150, 104, 70], [230, 225, 215]], float)
    pos = f * (len(paleta) - 1)
    i = np.clip(np.floor(np.nan_to_num(pos)).astype(int), 0, len(paleta) - 2)
    t = np.nan_to_num(pos) - i
    rgb = paleta[i] * (1 - t[..., None]) + paleta[i + 1] * t[..., None]
    rgb *= (0.35 + 0.65 * np.nan_to_num(cien))[..., None]
    out = np.zeros(Z.shape + (4,), np.uint8)
    out[..., :3] = np.clip(rgb, 0, 255)
    out[..., 3] = np.where(ok, 255, 0)
    return out


def do_gpkg(plik, dtm, srs=(-1, "undefined")):
    """Dopisuje warstwy terenu do GeoPackage (plik musi już istnieć albo
    zostanie założony). Zwraca liczbę warstwic."""
    import pandas as pd
    import lts_gpkg as G
    N = lambda n: G.WARSTWY_EN.get(n, n) if J.EN else n   # noqa: E731
    Zp = dtm["Z"][::-1]                         # wiersz 0 = północ
    sp, _ = pochodne(dtm)
    con = G._otworz(plik, srs)
    try:
        _przygotuj(con)
        for n in ("teren_wysokosc", "teren_spadek", "teren_cieniowanie"):
            inna = G.WARSTWY_EN.get(n) if not J.EN else n
            if inna and inna != N(n):
                _usun(con, inna)
        lo = float(np.floor(np.nanmin(dtm["Z"])))
        _raster(con, N("teren_wysokosc"), dtm, Zp, G.id_ukladu(srs),
                J.t("wysokość terenu [m]", "terrain elevation [m]"),
                {"scale": 0.001, "offset": lo, "uom": "m",
                 "pole": J.t("wysokosc", "elevation")})
        _raster(con, N("teren_spadek"), dtm, sp[::-1], G.id_ukladu(srs),
                J.t("spadek terenu [°]", "terrain slope [°]"),
                {"scale": 0.01, "offset": 0.0, "uom": "deg",
                 "pole": J.t("spadek", "slope")})
        _raster(con, N("teren_cieniowanie"), dtm,
                _kolory(Zp, cieniowanie(dtm)[::-1]), G.id_ukladu(srs),
                J.t("cieniowanie terenu", "terrain hillshade"))
        con.commit()
    finally:
        con.close()
    co = interwal(dtm)
    linie = warstwice(dtm, co)
    if linie:
        glowna = 5 * co
        G.zapisz_warstwe(
            plik, "warstwice", "LINESTRING", [l for _, l in linie],
            pd.DataFrame({"wysokosc_m": [round(z, 2) for z, _ in linie],
                          "glowna": [abs(z / glowna - round(z / glowna))
                                     < 1e-6 for z, _ in linie]}),
            z=True, srs=srs,
            opis=J.t(f"warstwice co {co:g} m", f"contours every {co:g} m"))
    return len(linie)
