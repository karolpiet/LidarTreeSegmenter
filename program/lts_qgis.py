"""Wygląd warstw w QGIS: domyślne style w GeoPackage i gotowy projekt.

Bez stylów QGIS rysuje każdą warstwę losowym, pełnym kolorem, więc
krzewy zakrywają resztę, a punkty plastrów robią plamę. Tu:

  zapisz_style(gpkg)   - tabela layer_styles w GeoPackage; QGIS sam bierze
                         z niej styl, gdy dodajesz warstwę (przeciągnięcie
                         pliku do okna też)
  zapisz_projekt(gpkg) - <skan>.qgs obok GeoPackage: kolejność warstw
                         (teren na dole, drzewa na górze), które są
                         włączone, style rastrów; otwiera się dwuklikiem

Style są pisane ręcznie w formacie QML (XML stylów QGIS) - bez QGIS na
komputerze, na którym liczy się skan.
"""
import datetime as dt
import sqlite3
import uuid
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import lts_jezyk as J
import lts_gpkg as G


# ----------------------------------------------------------------------
# klocki QML
# ----------------------------------------------------------------------
def _opt(**kw):
    return "".join(f'<Option name="{k}" type="QString" value={quoteattr(str(v))}/>'
                   for k, v in kw.items())


def _ddp(**wyr):
    """Właściwości liczone z pól (np. wielkość znaku z pierśnicy)."""
    if not wyr:
        return ""
    p = "".join(
        f'<Option name="{k}" type="Map"><Option name="active" type="bool" '
        f'value="true"/><Option name="expression" type="QString" '
        f'value={quoteattr(v)}/><Option name="type" type="int" value="3"/>'
        f'</Option>' for k, v in wyr.items())
    return ('<data_defined_properties><Option type="Map"><Option name="name" '
            'type="QString" value=""/><Option name="properties" type="Map">'
            f'{p}</Option><Option name="type" type="QString" '
            'value="collection"/></Option></data_defined_properties>')


def _symbol(rodzaj, nazwa, klasa, opcje, ddp="", alfa=1):
    return (f'<symbol type="{rodzaj}" name="{nazwa}" alpha="{alfa}" '
            f'clip_to_extent="1" force_rhr="0"><layer class="{klasa}" '
            f'enabled="1" pass="0" locked="0"><Option type="Map">{opcje}'
            f'</Option>{ddp}</layer></symbol>')


def linia(nazwa, kolor, grubosc=0.3, styl="solid"):
    return _symbol("line", nazwa, "SimpleLine", _opt(
        line_color=kolor, line_width=grubosc, line_width_unit="MM",
        line_style=styl, capstyle="round", joinstyle="round"))


def obrys(nazwa, kolor, grubosc=0.3, styl="solid", wypelnienie=None):
    return _symbol("fill", nazwa, "SimpleFill", _opt(
        color=wypelnienie or "0,0,0,0",
        style="solid" if wypelnienie else "no",
        outline_color=kolor, outline_width=grubosc,
        outline_width_unit="MM", outline_style=styl))


def znak(nazwa, kolor, rozmiar=2.0, ksztalt="circle", obw="35,35,35,255",
         obw_gr=0.2, ddp=""):
    return _symbol("marker", nazwa, "SimpleMarker", _opt(
        name=ksztalt, color=kolor, outline_color=obw,
        outline_width=obw_gr, outline_width_unit="MM", size=rozmiar,
        size_unit="MM", outline_style="solid" if obw_gr else "no"), ddp)


def jeden(symbol):
    return (f'<renderer-v2 type="singleSymbol" symbollevels="0" '
            f'forceraster="0" enableorderby="0"><symbols>{symbol}</symbols>'
            f'</renderer-v2>')


def kategorie(pole, lista, reszta=None):
    """lista: (wartość, etykieta, funkcja_symbolu(nazwa))."""
    if reszta:
        lista = list(lista) + [("", reszta[0], reszta[1])]
    kat = "".join(f'<category value={quoteattr(str(w))} symbol="{i}" '
                  f'label={quoteattr(e)} render="true"/>'
                  for i, (w, e, _) in enumerate(lista))
    sym = "".join(f(str(i)) for i, (_, _, f) in enumerate(lista))
    return (f'<renderer-v2 type="categorizedSymbol" attr={quoteattr(pole)} '
            f'symbollevels="0" forceraster="0" enableorderby="0">'
            f'<categories>{kat}</categories><symbols>{sym}</symbols>'
            f'</renderer-v2>')


def reguly(lista):
    """lista: (wyrażenie albo "ELSE", etykieta, funkcja_symbolu(nazwa))."""
    r = "".join(f'<rule key="r{i}" filter={quoteattr(w)} symbol="{i}" '
                f'label={quoteattr(e)}/>' for i, (w, e, _) in enumerate(lista))
    sym = "".join(f(str(i)) for i, (_, _, f) in enumerate(lista))
    return (f'<renderer-v2 type="RuleRenderer" symbollevels="0" '
            f'forceraster="0" enableorderby="0"><rules key="root">{r}'
            f'</rules><symbols>{sym}</symbols></renderer-v2>')


def etykiety(wyrazenie, rozmiar=8, kolor="20,20,20,255", odl=1.0,
             liniowe=False):
    pl = 'placement="2" placementFlags="10"' if liniowe else \
        f'placement="0" dist="{odl}" distUnits="MM"'
    return ('<labeling type="simple"><settings calloutType="simple">'
            f'<text-style fieldName={quoteattr(wyrazenie)} isExpression="1" '
            f'fontSize="{rozmiar}" fontSizeUnit="Point" '
            f'textColor="{kolor}" fontFamily="Arial" textOpacity="1">'
            '<text-buffer bufferDraw="1" bufferSize="0.7" bufferSizeUnits="MM" '
            'bufferColor="255,255,255,220" bufferOpacity="1"/></text-style>'
            f'<placement {pl} repeatDistance="60" repeatDistanceUnits="MM"/>'
            '<rendering obstacle="1" scaleVisibility="0" fontLimitPixelSize="0"'
            ' displayAll="0"/></settings></labeling>')


def qml(render, label="", maks_skala=None):
    """Cały styl QML. maks_skala: warstwa widoczna dopiero po przybliżeniu
    (mianownik skali, np. 400 = od 1:400 w dół)."""
    sk = (f'hasScaleBasedVisibilityFlag="1" maxScale="0" '
          f'minScale="{maks_skala}"') if maks_skala else \
        'hasScaleBasedVisibilityFlag="0"'
    return (f'<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>'
            f'<qgis version="3.34" styleCategories="AllStyleCategories" {sk} '
            f'labelsEnabled="{1 if label else 0}">{render}{label}</qgis>')


# ----------------------------------------------------------------------
# style warstw LidarTreeSegmenter (nazwy warstw i pól po polsku; po angielsku
# tłumaczone przy zapisie)
# ----------------------------------------------------------------------
BRAZ, ZIELONY, POMAR = "139,90,43,255", "46,125,50,255", "230,140,30,255"


def _gatunki():
    kol = (("świerk", "26,94,32,255"), ("buk", "214,120,30,255"),
           ("jodła", "40,120,110,255"), ("sosna", "120,150,40,255"),
           ("modrzew", "170,170,40,255"), ("jawor", "200,70,70,255"),
           ("dąb", "130,80,40,255"), ("jesion", "160,110,170,255"))
    return [(J.gatunek(g), J.gatunek(g), lambda n, k=k: znak(
        n, k, 2.4, ddp=_ddp(size=_wielkosc()))) for g, k in kol]


def _wielkosc():
    p = _pole("piersnica_cm")
    return f'coalesce(max(1.4, "{p}" / 18.0), 1.6)'


def _pole(n):
    return G.POLA_EN.get(n, n) if J.EN else n


def _tak():
    return J.TAK


def style():
    """{warstwa: (qml, widoczna w projekcie)} w kolejności od dołu."""
    # punkty plastra jednym kolorem (bez rozbijania na pień / gałęzie /
    # ulistnienie / podszyt - pole czesc zostaje w tabeli atrybutów)
    punkty = lambda k: qml(jeden(znak("0", k, 0.6, obw_gr=0)),  # noqa
                           maks_skala=400)
    gat = _pole("gatunek")
    s = {
        "teren_cieniowanie": (None, True),
        "teren_wysokosc": (None, False),
        "teren_spadek": (None, False),
        "warstwice": (qml(reguly([
            (f'"{_pole("glowna")}" = 1', J.t("warstwica główna",
                                             "index contour"),
             lambda n: linia(n, "90,55,20,255", 0.5)),
            ("ELSE", J.t("warstwica", "contour"),
             lambda n: linia(n, "90,55,20,200", 0.2))]),
            etykiety(f'if("{_pole("glowna")}" = 1, '
                     f'format_number("{_pole("wysokosc_m")}", 0), \'\')',
                     7, "110,70,30,255", liniowe=True)), True),
        "krzewy": (qml(jeden(obrys("0", "142,68,173,230", 0.35,
                                   wypelnienie="155,89,182,90")),
                    etykiety(f'format_number("{_pole("wysokosc_m")}", 1) '
                             f"|| ' m'", 6, "110,40,140,255")), True),
        "sciezka_skanera": (qml(jeden(linia("0", "255,190,0,255", 0.6))),
                            True),
        "punkty_3m": (punkty("40,90,200,255"), False),
        "punkty_1_3m": (punkty("220,30,30,255"), False),
        "przekroj_3m": (qml(jeden(obrys("0", "40,90,200,255", 0.35))),
                        False),
        "przekroj_1_3m": (qml(jeden(obrys("0", "220,30,30,255", 0.4))),
                          True),
        "etykiety_skanera": (qml(kategorie(_pole("przypisana"), [
            (_tak(), J.t("przypisana do drzewa", "assigned to a tree"),
             lambda n: znak(n, "30,110,220,255", 2.0, "triangle"))],
            reszta=(J.t("bez drzewa", "no tree"),
                    lambda n: znak(n, "220,40,40,255", 2.0, "triangle")))
            , etykiety(f'"{_pole("kod")}"', 7, "30,60,140,255")), True),
        "drzewa": (qml(kategorie(gat, _gatunki(), reszta=(
            J.t("inny / nieokreślony", "other / unspecified"),
            lambda n: znak(n, "150,150,150,255", 2.0,
                           ddp=_ddp(size=_wielkosc())))),
            etykiety(f'"{_pole("nr")}"', 7)), True),
        # _georef.gpkg
        "odchylki_gps": (qml(jeden(linia("0", "220,30,30,255", 0.5))), True),
        "pomiar_terenowy": (qml(jeden(znak("0", "30,90,220,255", 2.6,
                                           "triangle")),
                            etykiety(f'"{_pole("nr_teren")}"', 8,
                                     "30,60,160,255")), True),
    }
    return s


def _nazwa(n):
    return G.WARSTWY_EN.get(n, n) if J.EN else n


def _warstwy(plik):
    con = sqlite3.connect(str(plik))
    try:
        return dict(con.execute("SELECT table_name, data_type FROM "
                                "gpkg_contents").fetchall())
    finally:
        con.close()


# ----------------------------------------------------------------------
# style w GeoPackage (tabela layer_styles, czyta ją QGIS)
# ----------------------------------------------------------------------
def zapisz_style(plik):
    plik = Path(plik)
    if not plik.exists():
        return 0
    jest = _warstwy(plik)
    con = sqlite3.connect(str(plik))
    n = 0
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS layer_styles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, f_table_catalog TEXT(256),
            f_table_schema TEXT(256), f_table_name TEXT(256),
            f_geometry_column TEXT(256), styleName TEXT(30), styleQML TEXT,
            styleSLD TEXT, useAsDefault BOOLEAN, description TEXT,
            owner TEXT(30), ui TEXT(30), update_time DATETIME DEFAULT
            (strftime('%Y-%m-%dT%H:%M:%fZ','now')))""")
        if not con.execute("SELECT 1 FROM gpkg_contents WHERE table_name="
                           "'layer_styles'").fetchone():
            con.execute("INSERT INTO gpkg_contents (table_name, data_type, "
                        "identifier, last_change) VALUES ('layer_styles', "
                        "'attributes', 'layer_styles', ?)",
                        (dt.datetime.utcnow().strftime(
                            "%Y-%m-%dT%H:%M:%S.000Z"),))
        for pl, (styl, _) in style().items():
            nw = _nazwa(pl)
            if styl is None or jest.get(nw) != "features":
                continue
            con.execute("DELETE FROM layer_styles WHERE f_table_name=?",
                        (nw,))
            con.execute("INSERT INTO layer_styles (f_table_catalog, "
                        "f_table_schema, f_table_name, f_geometry_column, "
                        "styleName, styleQML, styleSLD, useAsDefault, "
                        "description, owner) VALUES ('', '', ?, 'geom', ?, "
                        "?, '', 1, ?, '')",
                        (nw, J.NAZWA, styl, J.t("styl LidarTreeSegmenter",
                                                 f"{J.NAZWA} style")))
            n += 1
        con.commit()
    finally:
        con.close()
    return n


# ----------------------------------------------------------------------
# projekt QGIS (.qgs) obok GeoPackage
# ----------------------------------------------------------------------
def _raster_pipe(pl, zakres):
    """Styl rastra (pseudokolor) dla wysokości i spadku."""
    if pl == "teren_spadek":
        lo, hi = 0, 45
        kolory = ("255,255,204", "254,217,118", "253,141,60", "227,26,28",
                  "128,0,38")
    elif pl == "teren_wysokosc" and zakres:
        lo, hi = zakres
        kolory = ("44,123,182", "171,221,164", "255,255,191", "253,174,97",
                  "215,25,28")
    else:
        return ""
    it = "".join(
        f'<item alpha="255" value="{lo + (hi - lo) * i / (len(kolory) - 1):.3f}"'
        f' label="{lo + (hi - lo) * i / (len(kolory) - 1):.1f}" '
        f'color="#{"".join(f"{int(c):02x}" for c in k.split(","))}"/>'
        for i, k in enumerate(kolory))
    return (f'<pipe><rasterrenderer type="singlebandpseudocolor" band="1" '
            f'opacity="0.75" alphaBand="-1" classificationMin="{lo}" '
            f'classificationMax="{hi}"><rastershader><colorrampshader '
            f'colorRampType="INTERPOLATED" classificationMode="1" '
            f'clip="0" minimumValue="{lo}" maximumValue="{hi}">{it}'
            f'</colorrampshader></rastershader></rasterrenderer></pipe>')


def _zakres_wysokosci(plik, nw):
    try:
        con = sqlite3.connect(str(plik))
        r = con.execute("SELECT MIN(min), MAX(max) FROM "
                        "gpkg_2d_gridded_tile_ancillary WHERE tpudt_name=?",
                        (nw,)).fetchone()
        con.close()
        return (float(r[0]), float(r[1])) if r and r[0] is not None else None
    except sqlite3.Error:
        return None


def zapisz_projekt(plik):
    """<skan>.qgs obok <skan>.gpkg. Zwraca ścieżkę albo None."""
    plik = Path(plik)
    if not plik.exists():
        return None
    jest = _warstwy(plik)
    srs = None
    con = sqlite3.connect(str(plik))
    try:
        r = con.execute("SELECT s.srs_id, s.organization, "
                        "s.organization_coordsys_id, s.definition FROM "
                        "gpkg_contents c JOIN gpkg_spatial_ref_sys s ON "
                        "c.srs_id = s.srs_id WHERE c.data_type='features' "
                        "LIMIT 1").fetchone()
        if r:
            srs = r
        ext = con.execute("SELECT MIN(min_x), MIN(min_y), MAX(max_x), "
                          "MAX(max_y) FROM gpkg_contents WHERE data_type="
                          "'features' AND table_name IN ('drzewa', 'trees')"
                          ).fetchone()
    finally:
        con.close()
    if srs and srs[1] and srs[1].upper() == "EPSG" and srs[2] > 0:
        crs = (f'<spatialrefsys><wkt>{escape(srs[3])}</wkt>'
               f'<authid>EPSG:{srs[2]}</authid></spatialrefsys>')
    else:                              # lokalny układ skanu w metrach
        crs = (f'<spatialrefsys><wkt>{escape(G.LOKALNY_WKT)}</wkt>'
               f'<description>{escape(J.t("LidarTreeSegmenter - lokalny układ skanu", "LidarTreeSegmenter - local scan system"))}'
               f'</description></spatialrefsys>')
    warstwy, drzewo = [], []
    for pl, (styl, wid) in style().items():
        nw = _nazwa(pl)
        typ = jest.get(nw)
        if typ is None:
            continue
        lid = f"{nw}_{uuid.uuid4().hex[:8]}"
        zrodlo = f"./{plik.name}"
        if typ == "features":
            ds = f"{zrodlo}|layername={nw}"
            prov, rodzaj = "ogr", "vector"
            body = styl[styl.index("<qgis"):]
            body = body[body.index(">") + 1:body.rindex("</qgis>")]
            sk = 'hasScaleBasedVisibilityFlag="1" maxScale="0" minScale="400"' \
                if 'minScale="400"' in styl else \
                'hasScaleBasedVisibilityFlag="0"'
            lab = 'labelsEnabled="1"' if "<labeling" in styl else ""
        else:
            ds = f"GPKG:{zrodlo}:{nw}"
            prov, rodzaj = "gdal", "raster"
            body = _raster_pipe(pl, _zakres_wysokosci(plik, nw))
            sk, lab = 'hasScaleBasedVisibilityFlag="0"', ""
        warstwy.append(
            f'<maplayer type="{rodzaj}" {sk} {lab} autoRefreshMode="Disabled">'
            f'<id>{lid}</id><datasource>{escape(ds)}</datasource>'
            f'<layername>{escape(nw)}</layername><srs>{crs}</srs>'
            f'<provider encoding="UTF-8">{prov}</provider>{body}</maplayer>')
        drzewo.append(
            f'<layer-tree-layer id="{lid}" name={quoteattr(nw)} '
            f'source={quoteattr(ds)} providerKey="{prov}" '
            f'checked="{"Qt::Checked" if wid else "Qt::Unchecked"}" '
            f'expanded="0"/>')
    if not warstwy:
        return None
    zasieg = ""
    if ext and ext[0] is not None:
        m = 3
        zasieg = (f'<mapcanvas name="theMapCanvas"><units>meters</units>'
                  f'<extent><xmin>{ext[0] - m}</xmin><ymin>{ext[1] - m}</ymin>'
                  f'<xmax>{ext[2] + m}</xmax><ymax>{ext[3] + m}</ymax>'
                  f'</extent><destinationsrs>{crs}</destinationsrs>'
                  f'</mapcanvas>')
    tytul = plik.stem
    xml = (f'<!DOCTYPE qgis PUBLIC \'http://mrcc.com/qgis.dtd\' \'SYSTEM\'>\n'
           f'<qgis projectname={quoteattr(tytul)} version="3.34.0">'
           f'<title>{escape(tytul)}</title>'
           + f'<projectCrs>{crs}</projectCrs>'
           + '<layer-tree-group>'
           + "".join(reversed(drzewo))     # w QGIS pierwsza = na górze
           + '</layer-tree-group>'
           + zasieg
           + '<projectlayers>' + "".join(warstwy) + '</projectlayers>'
           + '<properties><Paths><Absolute type="bool">false</Absolute>'
             '</Paths></properties></qgis>\n')
    wyj = plik.with_suffix(".qgs")
    wyj.write_text(xml, encoding="utf-8")
    return wyj
