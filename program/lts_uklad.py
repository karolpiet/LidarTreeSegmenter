"""
LidarTreeSegmenter - porzadek w folderze wynikow jednego skanu.

  wyniki\\<skan>\\
    CZYTAJ_MNIE.txt          co gdzie lezy
    01_RAPORT\\               Excel, podsumowanie, gatunki do wpisania
    02_CHMURY\\               wszystkie .laz / .las
    03_TABELE\\               tabele .csv i ustawienia .json
    04_OBRAZY_DRZEW\\         obrazek kazdego drzewa
    05_DZIENNIK\\             zapis przebiegu z okna LidarTreeSegmenter
    06_WIDOK_3D\\             chmura w 3D do otwarcia w przeglądarce (.html)

Programy zapisuja pliki gdzie chca (krok 1 z tree_segmenter_tool zapisuje
wszystko luzem), a uporzadkuj() rozklada je potem do podfolderow.
plik() znajduje plik niezaleznie od tego, czy juz lezy w podfolderze.

Mozna tez uruchomic recznie, zeby uporzadkowac stare wyniki:
  python lts_uklad.py ..\\wyniki            (wszystkie skany)
  python lts_uklad.py ..\\wyniki\\<skan>
"""

import re
import sys
from pathlib import Path

import lts_jezyk as J

RAPORT = "01_RAPORT"
CHMURY = "02_CHMURY"
TABELE = "03_TABELE"
OBRAZY = "04_OBRAZY_DRZEW"
DZIENNIK = "05_DZIENNIK"
WIDOK = "06_WIDOK_3D"
PODFOLDERY = (RAPORT, CHMURY, TABELE, OBRAZY, DZIENNIK, WIDOK)

# pliki dla użytkownika: (nazwa po polsku, po angielsku); {n} = nazwa skanu.
# Wersja angielska zapisuje nazwy angielskie, a obie wersje znajdują pliki
# w obu językach (skan liczony po polsku otworzy się w wersji angielskiej).
NAZWY = {
    "raport": ("{n}_RAPORT.xlsx", "{n}_REPORT.xlsx"),
    "podsumowanie": ("00_PODSUMOWANIE.txt", "00_SUMMARY.txt"),
    "gatunki": ("{n}_gatunki.csv", "{n}_species.csv"),
    "sprawdzenie": ("{n}_sprawdzenie.csv", "{n}_review.csv"),
    "widok": ("{n}_chmura_3d.html", "{n}_cloud_3d.html"),
    "sprawdzanie": ("{n}_sprawdzanie.html", "{n}_review.html"),
    "czytaj": ("CZYTAJ_MNIE.txt", "README.txt"),
}


def nazwa_pliku(rodzaj, n=""):
    """Nazwa pliku w bieżącym języku."""
    return NAZWY[rodzaj][1 if J.EN else 0].format(n=n)


def pliki(kat, rodzaj, n=""):
    """Istniejące pliki danego rodzaju (oba języki), najnowszy na końcu.
    Raport Excel także w wersji z godziną (gdy poprzedni był otwarty)."""
    wyn = []
    for wz in NAZWY[rodzaj]:
        wz = wz.format(n=n)
        if rodzaj == "raport":
            for k in (Path(kat) / RAPORT, Path(kat)):
                wyn += list(k.glob(wz.replace(".xlsx", "*.xlsx"))) \
                    if k.is_dir() else []
        else:
            p = plik(kat, wz)
            if p.exists():
                wyn.append(p)
    return sorted(set(wyn), key=lambda f: f.stat().st_mtime)


def znajdz(kat, rodzaj, n=""):
    """Najnowszy istniejący plik danego rodzaju albo None."""
    p = pliki(kat, rodzaj, n)
    return p[-1] if p else None


def usun_inny_jezyk(kat, rodzaj, n=""):
    """Plik wygenerowany przez program w drugim języku jest nieaktualny,
    gdy właśnie zapisaliśmy nowy - kasujemy go, żeby nie mylił."""
    inna = NAZWY[rodzaj][0 if J.EN else 1].format(n=n)
    for p in {plik(kat, inna), Path(kat) / inna}:
        try:
            if p.is_file():
                p.unlink()
        except OSError:
            pass


def gdzie(nazwa):
    """Do ktorego podfolderu nalezy plik o tej nazwie."""
    n = nazwa.lower()
    if n.endswith((".xlsx", ".xls", ".gpkg", ".qgs", ".qgz")) \
            or n in ("00_podsumowanie.txt", "00_summary.txt") \
            or n.endswith(("_gatunki.csv", "_sprawdzenie.csv", "_pomiar.csv",
                           "_pomiar.gpx", "_pomiar.xlsx", "_species.csv",
                           "_review.csv", "_field.csv", "_field.gpx")):
        return RAPORT
    if re.search(r"_(sciezka|path)\.(las|laz|txt|csv|xyz|pts|asc|ply)$", n):
        return RAPORT                  # ścieżka skanera dołożona do wyników
    if n.endswith((".laz", ".las")):
        return CHMURY
    if n.endswith((".csv", ".json", ".npz")):
        return TABELE
    if n.endswith(".png"):
        return OBRAZY
    if n.endswith(".html"):
        return WIDOK
    if n.startswith("dziennik") and n.endswith(".txt"):
        return DZIENNIK
    return None


def plik(kat, nazwa):
    """Sciezka pliku: tam, gdzie juz lezy (podfolder albo luzem), a jesli
    go jeszcze nie ma - tam, gdzie powinien trafic."""
    kat = Path(kat)
    pod = gdzie(nazwa)
    if pod and (kat / pod / nazwa).exists():
        return kat / pod / nazwa
    if (kat / nazwa).exists():
        return kat / nazwa
    return kat / pod / nazwa if pod else kat / nazwa


def katalog(kat, pod):
    p = Path(kat) / pod
    p.mkdir(parents=True, exist_ok=True)
    return p


def uporzadkuj(kat):
    kat = Path(kat)
    if not kat.is_dir():
        return
    for f in list(kat.iterdir()):
        if f.is_file():
            pod = gdzie(f.name)
            if pod:
                cel = katalog(kat, pod) / f.name
                if cel.exists() and cel.stat().st_mtime > f.stat().st_mtime:
                    f.unlink()            # w podfolderze jest nowsza wersja
                else:
                    f.replace(cel)
    stary = kat / "podglad"               # dawny folder obrazkow
    if stary.is_dir():
        for f in stary.glob("*.png"):
            cel = katalog(kat, OBRAZY) / f.name
            if cel.exists() and cel.stat().st_mtime > f.stat().st_mtime:
                f.unlink()
            else:
                f.replace(cel)
        try:
            stary.rmdir()
        except OSError:
            pass
    czytaj_mnie(kat)


def czytaj_mnie(kat):
    n = kat.name
    if J.EN:
        tekst = read_me(n)
    else:
        tekst = f"""WYNIKI SKANU {n}
{'=' * (13 + len(n))}

01_RAPORT\\
  {n}_RAPORT.xlsx       raport w Excelu: podsumowanie drzewostanu,
                        tabela drzew, ustawienia, objaśnienia
  00_PODSUMOWANIE.txt   to samo podsumowanie jako zwykły tekst
  {n}_gatunki.csv       tu wpisujesz gatunek drzew (np. świerk, buk;
                        kolumna gatunek_reczny), potem uruchom raport
                        jeszcze raz
  {n}.gpkg              GeoPackage do QGIS: drzewa, przekroje i punkty
                        na 1,3 m i 3 m, krzewy, teren
  {n}.qgs               projekt QGIS: otwórz dwuklikiem, warstwy już
                        ułożone i pokolorowane
  {n}_sprawdzenie.csv   Twoje decyzje ze sprawdzania drzew (zapisz go
                        tu z widoku 3D, potem "Przelicz raport")
  {n}_pomiar.csv        pomiar kilku drzew w terenie (Garmin); wzór:
                        LidarTreeSegmenter\\SZABLON_pomiar.csv
  {n}_georef.gpkg       GeoPackage we współrzędnych terenowych
                        (powstaje, gdy jest plik pomiaru)
  {n}_sciezka.*         ścieżka skanera (trajektoria), gdy nie leży
                        obok skanu: .las .laz .txt .csv .ply

02_CHMURY\\
  {n}_segmenty.laz      chmura z numerem drzewa przy każdym punkcie
  {n}_czesci.laz        chmura z podziałem na pień / gałęzie /
                        ulistnienie (CloudCompare: koloruj po "czesc")

03_TABELE\\
  {n}_drzewa.csv        drzewa z wykrywania: pozycja, pierśnica, wysokość
  {n}_czesci_drzewa.csv pień / gałęzie / ulistnienie, grupa gatunkowa
  {n}_pien_okregi.csv   przekroje pnia co 20 cm (krzywa zbieżystości)
  {n}_okregi.csv        przekroje pnia z wykrywania drzew
  {n}_ustawienia.json   ustawienia wykrywania (dla programu)
  {n}_ustawienia_lts.json  wybrany drzewostan i gatunek
  {n}_drzewa_raport.csv wszystkie drzewa z raportu (z krzewami)
  {n}_krzewy.csv        krzewy 0,3-4 m: położenie, pole, wysokość
  {n}_rozdzielone.csv   drzewa z dwoma pniami rozdzielone w kroku 2
  odrzucone_*.csv       drzewa odrzucone przez filtry

04_OBRAZY_DRZEW\\
  drzewo_001.png ...    obrazek każdego drzewa, numer jak w tabelach

05_DZIENNIK\\
  dziennik_*.txt        zapis przebiegu z okna LidarTreeSegmenter

06_WIDOK_3D\\
  {n}_chmura_3d.html    chmura w 3D: otwórz dwuklikiem w przeglądarce,
                        kliknij drzewo, żeby zobaczyć jego dane
  {n}_sprawdzanie.html  to samo, od razu w trybie sprawdzania drzew
                        po kolei (1 drzewo, 2 krzak, 3 złom, 4 świerk,
                        5 buk)
"""
    (kat / nazwa_pliku("czytaj")).write_text(tekst, encoding="utf-8")
    usun_inny_jezyk(kat, "czytaj")


def read_me(n):
    return f"""RESULTS OF SCAN {n}
{'=' * (16 + len(n))}

01_RAPORT\\  (report)
  {n}_REPORT.xlsx       Excel report: stand summary, tree table,
                        settings, explanations
  00_SUMMARY.txt        the same summary as plain text
  {n}_species.csv       enter the species of each tree here (e.g. spruce,
                        beech; column species_manual), then run the
                        report again
  {n}.gpkg              GeoPackage for QGIS: trees, cross-sections and
                        points at 1.3 m and 3 m, shrubs, terrain
  {n}.qgs               QGIS project: double-click to open, layers already
                        ordered and styled
  {n}_review.csv        your decisions from the tree review (save it here
                        from the 3D view, then "Recalculate report")
  {n}_field.csv         field measurement of a few trees (Garmin GPS);
                        template: LidarTreeSegmenter\\TEMPLATE_field_measurement.csv
                        (the Polish name {n}_pomiar.csv works too)
  {n}_georef.gpkg       GeoPackage in field coordinates
                        (created when a field measurement file exists)
  {n}_path.*            scanner path (trajectory), when it is not next to
                        the scan: .las .laz .txt .csv .ply

02_CHMURY\\  (point clouds)
  {n}_segmenty.laz      point cloud with a tree number for every point
  {n}_czesci.laz        point cloud split into stem / branches /
                        foliage (CloudCompare: colour by "czesc":
                        1 stem, 2 branches, 3 foliage, 4 understory)

03_TABELE\\  (working tables - read by the programs, column names stay
             in Polish in both language versions)
  {n}_drzewa.csv        trees from detection: position, DBH, height
  {n}_czesci_drzewa.csv stem / branches / foliage, species group
  {n}_pien_okregi.csv   stem cross-sections every 20 cm (taper curve)
  {n}_okregi.csv        stem cross-sections from tree detection
  {n}_ustawienia.json   detection settings (for the program)
  {n}_ustawienia_lts.json  chosen stand class and species
  {n}_drzewa_raport.csv all trees from the report (including shrubs)
  {n}_krzewy.csv        shrubs 0.3-4 m: position, area, height
  {n}_rozdzielone.csv   trees with two stems split in step 2
  odrzucone_*.csv       trees rejected by the filters

04_OBRAZY_DRZEW\\  (tree images)
  drzewo_001.png ...    image of every tree, numbered as in the tables

05_DZIENNIK\\  (log)
  dziennik_*.txt        log of the run from the LidarTreeSegmenter window

06_WIDOK_3D\\  (3D view)
  {n}_cloud_3d.html     3D point cloud: double-click to open it in a
                        browser, click a tree to see its data
  {n}_review.html       the same, opened directly in tree review mode
                        (1 tree, 2 shrub, 3 snag, 4 spruce, 5 beech)
"""


def to_skan(p):
    return any(p.glob("*_drzewa.csv")) or any(p.glob("*_segmenty.laz")) \
        or any((p / x).is_dir() for x in PODFOLDERY)


if __name__ == "__main__":
    for a in sys.argv[1:] or ["."]:
        p = Path(a)
        skany = [p] if to_skan(p) else sorted(
            d for d in p.iterdir() if d.is_dir() and to_skan(d))
        for s in skany:
            uporzadkuj(s)
            print(J.t(f"uporzadkowano: {s}", f"sorted: {s}"))
