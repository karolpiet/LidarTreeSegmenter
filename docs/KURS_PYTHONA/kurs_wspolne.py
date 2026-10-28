"""
KURS PYTHONA Z PROGRAMEM LidarTreeSegmenter - wspólne narzędzia (nasza "skrzynka z narzędziami")
=========================================================================

Ten plik NIE jest lekcją, którą się uruchamia. To MODUŁ: zbiór funkcji,
które piszemy raz, a używamy w lekcjach 6-10. W lekcji wystarczy napisać

    import kurs_wspolne as KW
    chmura = KW.wczytaj_chmure(sciezka)

i mamy wczytaną chmurę. Wszystkie te funkcje poznasz po kolei
w lekcjach 1-5 - tu są tylko zebrane w jednym miejscu.

Ważne: ten plik musi leżeć w TYM SAMYM folderze co pliki lekcji.
"""

import sys
from pathlib import Path

import numpy as np

try:
    import laspy
except ImportError:
    sys.exit("BŁĄD: brak biblioteki laspy. Zainstaluj ją poleceniem:\n"
             "      python -m pip install laspy lazrs")

# Nazwy pól, pod którymi LidarTreeSegmenter zapisuje numer drzewa i wysokość nad gruntem
# (tak samo jak w program\10_pien_galezie_liscie.py)
POLA_DRZEWA = ("treeID", "treeID_pred", "tree_id", "instance")
POLA_WYSOKOSCI = ("wys_nad_grunt", "hag", "HeightAboveGround")
NAZWY_CZESCI = {0: "nic", 1: "pień", 2: "gałęzie", 3: "liście", 4: "podszyt"}


# ----------------------------------------------------------------------
def sciezka_z_argumentu(przyklad="python lekcja.py <plik.laz>"):
    """Bierze ścieżkę pliku z konsoli (sys.argv[1]) i sprawdza, czy plik
    istnieje. Gdy czegoś brakuje - kończy program z jasnym komunikatem."""
    if len(sys.argv) < 2:
        sys.exit("BŁĄD: nie podano pliku z chmurą punktów.\n"
                 f"      Uruchom tak:  {przyklad}\n"
                 "      Wskazówka: wpisz początek polecenia, a potem PRZECIĄGNIJ\n"
                 "      plik .laz z Eksploratora do okna konsoli - Windows sam\n"
                 "      wpisze pełną ścieżkę. Na końcu naciśnij Enter.")
    sciezka = Path(sys.argv[1].strip('"'))
    if not sciezka.exists():
        sys.exit(f"BŁĄD: nie ma takiego pliku: {sciezka}\n"
                 "      Sprawdź, czy nie ma literówki w ścieżce.")
    return sciezka


# ----------------------------------------------------------------------
def wysokosc_nad_gruntem(xyz, komorka=1.0):
    """Bardzo prosty model terenu (lekcja 4): w każdej komórce siatki
    komorka × komorka metrów najniższy punkt to grunt. Wysokość nad
    gruntem = z punktu - z gruntu w jego komórce."""
    x, y, z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    kol = ((x - x.min()) / komorka).astype(np.int64)
    wie = ((y - y.min()) / komorka).astype(np.int64)
    siatka = np.full((wie.max() + 1, kol.max() + 1), np.inf)
    np.minimum.at(siatka, (wie, kol), z)      # najniższe z w każdej komórce
    return z - siatka[wie, kol]


# ----------------------------------------------------------------------
def wczytaj_chmure(sciezka):
    """Wczytuje .las/.laz i zwraca słownik:
        xyz    - tablica N × 3 (metry)
        drzewo - numer drzewa każdego punktu albo None (surowy skan)
        czesc  - 0 nic, 1 pień, 2 gałęzie, 3 liście, 4 podszyt albo None
        h      - wysokość nad gruntem (z pliku albo policzona w przybliżeniu)
        opis   - krótki opis, co znaleziono w pliku
    """
    print(f"Wczytuję {Path(sciezka).name} ...", flush=True)
    las = laspy.read(str(sciezka))
    pola = set(las.point_format.dimension_names)

    xyz = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                           np.asarray(las.z)])
    opis = []

    pole_drzewa = next((p for p in POLA_DRZEWA if p in pola), None)
    drzewo = None
    if pole_drzewa:
        drzewo = np.asarray(las[pole_drzewa]).astype(np.int64)
        opis.append(f"numer drzewa z pola '{pole_drzewa}'")

    czesc = None
    if "czesc" in pola:
        czesc = np.asarray(las["czesc"]).astype(np.uint8)
        opis.append("części drzewa z pola 'czesc'")

    pole_wys = next((p for p in POLA_WYSOKOSCI if p in pola), None)
    if pole_wys:
        h = np.asarray(las[pole_wys], dtype=np.float64)
        opis.append(f"wysokość nad gruntem z pola '{pole_wys}'")
    else:
        h = wysokosc_nad_gruntem(xyz)
        opis.append("wysokość nad gruntem POLICZONA w przybliżeniu (siatka 1 m)")

    del las                                  # zwalniamy pamięć
    print(f"  punktów: {len(xyz):,}".replace(",", " "))
    for o in opis:
        print("  -", o)
    return {"xyz": xyz, "drzewo": drzewo, "czesc": czesc, "h": h,
            "opis": opis, "nazwa": Path(sciezka).stem}


# ----------------------------------------------------------------------
def okrag_kasa(x, y):
    """Okrąg metodą najmniejszych kwadratów (Kåsa) - lekcja 6.
    Zwraca (srodek_x, srodek_y, promien) albo None."""
    if len(x) < 3:
        return None
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x * x + y * y
    c, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = c[0] / 2, c[1] / 2
    r2 = c[2] + cx * cx + cy * cy
    if r2 <= 0:
        return None
    return cx, cy, float(np.sqrt(r2))


def okrag_odporny(x, y, powtorzenia=3):
    """Kåsa kilka razy z rzędu: po każdym dopasowaniu wyrzucamy punkty,
    które leżą daleko od okręgu (gałązki, liście), i liczymy jeszcze raz."""
    wynik = okrag_kasa(x, y)
    for _ in range(powtorzenia):
        if wynik is None:
            return None
        cx, cy, r = wynik
        odl = np.abs(np.hypot(x - cx, y - cy) - r)   # odległość od okręgu
        dobre = odl < max(0.01, 2 * odl.std())
        if dobre.sum() < 10:
            break
        x, y = x[dobre], y[dobre]
        wynik = okrag_kasa(x, y)
    return wynik


# ----------------------------------------------------------------------
def wybierz_drzewo(chm, nr=None):
    """Zwraca (numer, indeksy_punktow) jednego drzewa.
    nr = None -> wybieramy sami: drzewo wyższe niż 10 m z największą
    liczbą punktów pnia w plastrze 1,3 m. Gdy chmura nie ma numerów drzew
    (surowy skan) - bierzemy okolicę najgęstszego miejsca w plastrze 1,3 m
    (promień 3 m) i nazywamy ją "drzewem 0"."""
    xyz, h, drzewo, czesc = chm["xyz"], chm["h"], chm["drzewo"], chm["czesc"]
    plaster = np.abs(h - 1.3) <= 0.05

    if drzewo is None:
        p = xyz[plaster]
        if len(p) == 0:
            sys.exit("BŁĄD: w plastrze 1,3 m nie ma punktów.")
        # najgęstsza komórka 25 × 25 cm w plastrze = prawdopodobnie pień
        kom = np.floor(p[:, :2] / 0.25).astype(np.int64)
        klucze, ile = np.unique(kom, axis=0, return_counts=True)
        cx, cy = (klucze[np.argmax(ile)] + 0.5) * 0.25
        blisko = np.hypot(xyz[:, 0] - cx, xyz[:, 1] - cy) <= 3.0
        print(f"  brak numerów drzew - biorę okolicę X={cx:.1f}, Y={cy:.1f}")
        return 0, np.flatnonzero(blisko)

    if nr is None:
        dobre = (drzewo > 0)
        n_max = int(drzewo.max()) + 1
        wys = np.zeros(n_max)
        np.maximum.at(wys, drzewo[dobre], h[dobre])
        w_plastrze = plaster & dobre
        if czesc is not None:
            w_plastrze &= (czesc == 1)
        ile = np.bincount(drzewo[w_plastrze], minlength=n_max).astype(float)
        ile[wys < 10] = 0
        ile[0] = 0
        nr = int(np.argmax(ile))
        print(f"  nie podano numeru drzewa - wybieram drzewo {nr}")
    idx = np.flatnonzero(drzewo == nr)
    if len(idx) == 0:
        dostepne = np.unique(drzewo[drzewo > 0])
        sys.exit(f"BŁĄD: nie ma drzewa nr {nr}. Numery w pliku: "
                 f"{dostepne.min()} .. {dostepne.max()}")
    return nr, idx


def folder_wynikow():
    """Folder 'wyniki_kursu' w bieżącym folderze - tu zapisujemy obrazki,
    tabele i chmury z ćwiczeń."""
    f = Path("wyniki_kursu")
    f.mkdir(exist_ok=True)
    return f
