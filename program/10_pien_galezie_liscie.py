"""
PODZIAL DRZEWA NA PIEN, GALEZIE I ULISTNIENIE
=============================================

Bierze chmure, w ktorej kazdy punkt ma juz numer drzewa, i kazdemu punktowi
dopisuje, CZYM jest:

    czesc = 1   pien
    czesc = 2   galezie (drewno poza pniem)
    czesc = 3   ulistnienie (liscie, igly, drobne galazki)
    czesc = 0   nic z tego (grunt, punkty bez drzewa)

oraz liczbe p_drewno (0..1) - jak bardzo punkt wyglada na drewno.

ZERO recznie oznaczonych danych. Model uczy sie sam na kazdej chmurze:

  KROK 1  Wczytanie chmury z numerami drzew i wysokoscia nad gruntem
  KROK 2  PIEN: sledzenie okregow od podstawy w gore, plaster po plastrze
  KROK 3  Cechy geometryczne kazdego punktu (czy lezy na linii, plaszczyznie,
          czy w chmurze rozproszonej) w dwoch skalach
  KROK 4  Samouczenie: pewne przyklady drewna (pien + wyrazne galezie)
          i pewne przyklady lisci -> las losowy -> p_drewno dla wszystkich
  KROK 5  Sprzatanie: male, samotne kawalki "drewna" wiszace w koronie
          to w praktyce kepy lisci -> przenosimy je do ulistnienia
  KROK 6  Zapis: chmura .laz z polami czesc i p_drewno + tabele CSV

SKAD BRAC WEJSCIE
-----------------
Najlepiej z wyniku tree_segmenter_tool:

    ..\\tree_segmenter_tool\\results\\<skan>\\<skan>_segmenty.laz

(pola treeID_pred i wys_nad_grunt). Dziala tez na Twoich recznie
oznaczonych chmurach z DANE\\tree_conected (pole treeID, opcjonalnie hag).

URUCHOMIENIE
------------
    python 10_pien_galezie_liscie.py <chmura.laz>
    python 10_pien_galezie_liscie.py <chmura.laz> --bez-obrazkow

Wymagane biblioteki (te same co w tree_segmenter_tool):
    python -m pip install laspy lazrs numpy pandas scipy scikit-learn matplotlib
"""

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

import lts_jezyk as J

try:
    import laspy
    from scipy.spatial import cKDTree
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    from sklearn.ensemble import RandomForestClassifier
except ImportError as e:
    sys.exit(J.t(f"BLAD: brak biblioteki ({e.name}).\n",
               f"ERROR: missing library ({e.name}).\n") +
             "      python -m pip install laspy lazrs numpy pandas scipy "
             "scikit-learn matplotlib")

TU = Path(__file__).resolve().parent       # LidarTreeSegmenter\\program
ROOT = TU.parent                          # LidarTreeSegmenter
sys.path.insert(0, str(TU))
import lts_uklad as U                    # noqa: E402
import lts_gpkg as G                     # noqa: E402
import lts_na_zywo as Z                  # noqa: E402
import lts_ustawienia as UST             # noqa: E402
import lts_sciezka as SC                 # noqa: E402
import lts_dtm as DTM                    # noqa: E402

POLA_DRZEWA = ("treeID_pred", "treeID", "tree_id", "instance")
POLA_WYSOKOSCI = ("wys_nad_grunt", "hag", "HeightAboveGround")

PIEN, GALEZ, LISC, PODSZYT = 1, 2, 3, 4
DORYSOWANY = "#2f6fd6"       # kolor zrekonstruowanego pnia na obrazkach
NAZWY = {0: "nic", PIEN: "pien", GALEZ: "galezie", LISC: "ulistnienie",
         PODSZYT: "podszyt"}
SMUKLOSC_KRZEWU = 20.0       # h/d poniżej tego przy niskim obiekcie: krzew,
SMUKLOSC_DO_WYS = 15.0       # pniak albo złom (dotyczy obiektów niższych)
ZLOM_PUSTY = 0.08            # gruby niski pień wyraźnie pusty = złom
                             # (złamane drzewo), liczony w wynikach


# ======================================================================
# PARAMETRY
# ======================================================================
class Parametry:

    # --- KROK 2: sledzenie pnia ------------------------------------
    PIEN_START = 1.0
    # Na jakiej wysokosci nad gruntem szukamy pnia najpierw. 1 m jest nad
    # nabiegami korzeniowymi i zwykle pod pierwszymi galeziami.

    PIEN_KROK = 0.20
    # Grubosc plastra. Cienszy = dokladniejszy pien, ale mniej punktow
    # w plastrze (gorzej przy slabo zeskanowanych pniach).

    PIEN_MAX_PRZERWA = 6
    # Ile plastrow z rzedu moze sie nie udac (galaz zaslania pien, dziura
    # w skanie), zanim uznamy, ze pien sie skonczyl. 6 x 0.2 m = 1.2 m.

    PIEN_MIN_PROMIEN = 0.025
    # Ponizej 2.5 cm promienia to juz nie pien, tylko szczyt / przewodnik.

    PIEN_MAX_PRZESUNIECIE = 0.12
    # O ile metrow moze przesunac sie srodek pnia miedzy plastrami
    # (wzgledem przewidywanego polozenia).

    PIEN_ZMIANA_PROMIENIA = (0.70, 1.15)
    # Promien w plastrze wyzej musi miescic sie w tym zakresie wzgledem
    # poprzedniego. Pien sie zweza, wiec gora tylko lekko ponad 1.

    PIEN_SZEROKOSC_PASA = 0.02
    # Jak blisko okregu musi lezec punkt, zeby glosowal za tym okregiem
    # (RANSAC). Dla MLS z szumem 1-2 cm, 2 cm jest rozsadne.

    PIEN_MIN_POKRYCIE = 90.0
    # Minimalny luk (stopnie) widziany na okregu. Mniej = to raczej
    # kawalek galezi niz pien.

    PIEN_TOLERANCJA = 0.04

    PIEN_WYSOKOSCI_STARTU = (1.0, 2.0, 3.0, 4.0, 5.0, 6.5)
    # Na jakich wysokosciach szukamy pnia, zanim zaczniemy go sledzic.
    # Wyzej = ponad podszytem, gdzie pien jest czysty.

    PIEN_MAX_PROMIEN = 0.6
    # Najgrubszy dopuszczalny pien: promien 60 cm = piersnica 120 cm.
    # Punkt nalezy do pnia, gdy lezy nie dalej niz promien + tyle od osi.

    # --- KROK 3: cechy ----------------------------------------------
    VOXEL_CECH = 0.025
    # Cechy liczymy na chmurze przerzedzonej do tego voxela (2.5 cm),
    # a wynik przenosimy na wszystkie punkty. Bez tego 15 mln punktow
    # liczyloby sie bardzo dlugo.

    SASIEDZI_MALA_SKALA = 12
    SASIEDZI_DUZA_SKALA = 40
    # Dwie skale: mala widzi pojedyncza galazke, duza - ksztalt konaru.

    # --- KROK 4: samouczenie ----------------------------------------
    GALAZ_MIN_LINIOWOSC = 0.80
    GALAZ_MAX_ROZPROSZENIE = 0.04
    # Pewny przyklad galezi: punkt lezy na wyraznej linii w obu skalach.

    LISC_MIN_ROZPROSZENIE = 0.15
    LISC_MAX_LINIOWOSC = 0.50
    LISC_MIN_ODL_OD_PNIA = 0.5
    # Pewny przyklad lisci: punkty rozrzucone we wszystkich kierunkach,
    # bez wyraznego kierunku, z dala od pnia.

    MAX_PRZYKLADOW_NA_KLASE = 200_000
    PROG_DREWNA = 0.5
    # p_drewno powyzej progu = drewno. Podnies (np. 0.6), jesli za duzo
    # lisci jest oznaczanych jako galezie.

    # --- KROK 5: sprzatanie -----------------------------------------
    MIN_VOXELI_GALEZI = 25
    # Kawalek "drewna" niepolaczony z pniem i mniejszy niz tyle voxeli
    # (25 x 2.5 cm, czyli ok. 60 cm galazki) idzie do ulistnienia.

    MIN_WYSOKOSC = 0.3
    # Ponizej tej wysokosci nad gruntem nic nie klasyfikujemy (grunt, runo).


P = Parametry()


# ======================================================================
# KROK 1
# ======================================================================
def krok1_wczytaj(sciezka):
    print(J.t(f"\n[KROK 1] Wczytuje {sciezka.name}",
            f"\n[STEP 1] Loading {sciezka.name}"))
    las = laspy.read(str(sciezka))
    pola = {d.name for d in las.point_format.dimensions}

    pole_drzewa = next((p for p in POLA_DRZEWA if p in pola), None)
    if pole_drzewa is None:
        sys.exit(J.t(f"BLAD: w chmurze nie ma numeru drzewa "
                   f"(szukalem pol: {', '.join(POLA_DRZEWA)}).\n"
                   f"      Najpierw puszcz tree_segmenter_tool i podaj "
                   f"plik *_segmenty.laz.",
                   f"ERROR: the point cloud has no tree number "
                   f"(looked for fields: {', '.join(POLA_DRZEWA)}).\n"
                   f"      Run tree detection first and pass the "
                   f"*_segmenty.laz file."))
    xyz = np.column_stack([np.asarray(las.x), np.asarray(las.y),
                           np.asarray(las.z)])
    drzewo = np.asarray(las[pole_drzewa]).astype(np.int64)

    pole_wys = next((p for p in POLA_WYSOKOSCI if p in pola), None)
    if pole_wys:
        h = np.asarray(las[pole_wys], dtype=np.float64)
        print(J.t(f"         wysokosc nad gruntem z pola: {pole_wys}",
                f"         height above ground from field: {pole_wys}"))
    else:
        # Bez gruntu: liczymy od najnizszego punktu kazdego drzewa.
        # Dla pomiaru pnia wystarczy, ale wysokosci beda przyblizone.
        h = np.zeros(len(xyz))
        for t in np.unique(drzewo):
            m = drzewo == t
            h[m] = xyz[m, 2] - np.percentile(xyz[m, 2], 0.5)
        print(J.t("         UWAGA: brak wysokosci nad gruntem - licze od dolu "
                "kazdego drzewa (przyblizenie)",
                "         WARNING: no height above ground - measuring from "
                "the bottom of each tree (approximation)"))

    print(J.t(f"         punktow: {len(xyz):,}, pole drzewa: {pole_drzewa}, "
            f"drzew: {len(np.unique(drzewo[drzewo > 0]))}",
            f"         points: {len(xyz):,}, tree field: {pole_drzewa}, "
            f"trees: {len(np.unique(drzewo[drzewo > 0]))}"))
    return las, xyz, drzewo, h, pole_drzewa


# ======================================================================
# KROK 2 - PIEN
# ======================================================================
def okrag_algebraiczny(x, y):
    """Dopasowanie okregu metoda najmniejszych kwadratow (Kasa)."""
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x * x + y * y
    c, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = c[0] / 2, c[1] / 2
    r2 = c[2] + cx * cx + cy * cy
    return cx, cy, np.sqrt(r2) if r2 > 0 else 0.0


def pokrycie_katowe(x, y, cx, cy, n_sekt=36):
    kat = np.arctan2(y - cy, x - cx)
    sekt = ((kat + np.pi) / (2 * np.pi) * n_sekt).astype(int) % n_sekt
    return len(np.unique(sekt)) * 360.0 / n_sekt


def ransac_okrag(x, y, rng, r_min, r_max, kotwica=None, max_przes=None,
                 proby=200):
    """
    Szuka okregu, na ktorym lezy najwiecej punktow. Odporny na galezie
    i liscie w plastrze: one nie leza na zadnym wspolnym okregu.
    """
    n = len(x)
    if n < 8:
        return None
    pas = P.PIEN_SZEROKOSC_PASA
    # wszystkie proby naraz: okrag przez 3 losowe punkty
    i = rng.integers(0, n, size=(proby, 3))
    ax, bx, qx = x[i[:, 0]], x[i[:, 1]], x[i[:, 2]]
    ay, by, qy = y[i[:, 0]], y[i[:, 1]], y[i[:, 2]]
    d = 2 * (ax * (by - qy) + bx * (qy - ay) + qx * (ay - by))
    d = np.where(np.abs(d) < 1e-9, np.nan, d)
    a2, b2, q2 = ax*ax + ay*ay, bx*bx + by*by, qx*qx + qy*qy
    ux = (a2 * (by - qy) + b2 * (qy - ay) + q2 * (ay - by)) / d
    uy = (a2 * (qx - bx) + b2 * (ax - qx) + q2 * (bx - ax)) / d
    r = np.hypot(ax - ux, ay - uy)
    ok = (r >= r_min) & (r <= r_max)
    if kotwica is not None:
        ok &= np.hypot(ux - kotwica[0], uy - kotwica[1]) <= max_przes
    if not ok.any():
        return None
    ux, uy, r = ux[ok], uy[ok], r[ok]
    # glosowanie: ile punktow lezy w pasie wokol kazdego okregu
    ile = np.zeros(len(ux), int)
    for a in range(0, len(ux), 50):
        dd = np.hypot(x[None, :] - ux[a:a+50, None], y[None, :] - uy[a:a+50, None])
        ile[a:a+50] = (np.abs(dd - r[a:a+50, None]) < pas).sum(axis=1)
    j = int(np.argmax(ile))
    if ile[j] < 8:
        return None
    najlepszy = (ux[j], uy[j], r[j])
    ux, uy, r = najlepszy
    w = np.abs(np.hypot(x - ux, y - uy) - r) < pas
    cx, cy, rr = okrag_algebraiczny(x[w], y[w])
    if not (r_min <= rr <= r_max):
        cx, cy, rr = ux, uy, r
    blad = float(np.sqrt(np.mean((np.hypot(x[w] - cx, y[w] - cy) - rr) ** 2)))
    return dict(cx=cx, cy=cy, r=rr, n=int(w.sum()), blad=blad,
                pokrycie=pokrycie_katowe(x[w], y[w], cx, cy))


def znajdz_start(xyz, h, rng, dol):
    """
    Kandydaci na pien w plastrze [dol, dol+0.4 m]: zwarte klastry, na ktorych
    lezy dobry okrag. Zwraca liste okregow (moze byc pusta).
    """
    from sklearn.cluster import DBSCAN
    m = (h >= dol) & (h < dol + 0.4)
    if m.sum() < 15:
        return []
    p = xyz[m]
    if len(p) > 20000:
        p = p[rng.choice(len(p), 20000, replace=False)]
    et = DBSCAN(eps=0.08, min_samples=6).fit_predict(p[:, :2])
    kand = []
    for k in np.unique(et[et >= 0]):
        q = p[et == k]
        if len(q) < 15:
            continue
        o = ransac_okrag(q[:, 0], q[:, 1], rng, 0.03, P.PIEN_MAX_PROMIEN)
        if o and o["pokrycie"] >= 120 and o["blad"] < max(0.015, 0.12 * o["r"]):
            o["h"] = dol + 0.2
            kand.append(o)
    return kand


def idz(start, xyz, h, rng, kierunek, r_wzor=None):
    """
    Od okregu `start` idzie plaster po plastrze w gore (+1) albo w dol (-1)
    i w kazdym szuka okregu tam, gdzie pien POWINIEN byc (przedluzenie osi
    z kilku ostatnich plastrow).

    W DOL jest ostrzej niz w gore: tam czeka podszyt, ktory chetnie "udaje"
    coraz grubszy pien. Promien moze rosnac najwyzej o 10% na plaster
    i nie wiecej niz 35% ponad promien czystej czesci pnia (r_wzor).
    """
    hist = [start]
    przerwa = 0
    hc = start["h"]
    while True:
        hc += kierunek * P.PIEN_KROK
        if hc < P.MIN_WYSOKOSC or hc > h.max():
            break
        ost = hist[-6:]
        if len(ost) >= 3:
            hh = np.array([o["h"] for o in ost])
            px = np.polyval(np.polyfit(hh, [o["cx"] for o in ost], 1), hc)
            py = np.polyval(np.polyfit(hh, [o["cy"] for o in ost], 1), hc)
        else:
            px, py = ost[-1]["cx"], ost[-1]["cy"]
        r0 = ost[-1]["r"]
        if kierunek > 0:
            lo, hi = P.PIEN_ZMIANA_PROMIENIA
            r_lo, r_hi, min_pokr = r0 * lo, r0 * hi, P.PIEN_MIN_POKRYCIE
        else:
            r_lo, r_hi, min_pokr = r0 * 0.92, r0 * 1.10, 120.0
            if r_wzor:
                r_hi = min(r_hi, r_wzor * 1.35)
        o = None
        m = np.abs(h - hc) < P.PIEN_KROK / 2
        if m.any() and r_hi > r_lo:
            q = xyz[m]
            q = q[np.hypot(q[:, 0] - px, q[:, 1] - py) < r0 * 1.6 + 0.10]
            if len(q) >= 8:
                if len(q) > 4000:
                    q = q[rng.choice(len(q), 4000, replace=False)]
                o = ransac_okrag(q[:, 0], q[:, 1], rng, r_lo, r_hi,
                                 kotwica=(px, py),
                                 max_przes=P.PIEN_MAX_PRZESUNIECIE)
                if o and (o["pokrycie"] < min_pokr or
                          o["blad"] > max(0.02, 0.25 * o["r"])):
                    o = None
        if o is None:
            przerwa += 1
            if przerwa > P.PIEN_MAX_PRZERWA:
                break
            continue
        przerwa = 0
        o["h"] = hc
        hist.append(o)
        if o["r"] < P.PIEN_MIN_PROMIEN:
            break
    return hist[1:]


def ocena_lancucha(ok):
    """Ile okregow ma promien zgodny z mediana (+-30%) - im wiecej, tym pewniej."""
    if len(ok) < 3:
        return 0
    R = np.array([o["r"] for o in ok])
    return int((np.abs(R / np.median(R) - 1) < 0.3).sum())


def rekonstruuj_dol(ok):
    """
    Pien nie dochodzi do ziemi (zaslonil go podszyt): przedluzamy go w dol.
    Os - prosta dopasowana do dolnych 3 m zmierzonego pnia. Promien -
    zbieznosc z tego samego odcinka, ograniczona do rozsadnej (pien w dol
    grubieje 0 do 1.5 cm promienia na metr).
    """
    dol = [o for o in ok if o["h"] <= ok[0]["h"] + 3.0]
    H = np.array([o["h"] for o in dol])
    R = np.array([o["r"] for o in dol])
    if len(dol) >= 4 and np.ptp(H) > 0.5:
        fx = np.polyfit(H, [o["cx"] for o in dol], 1)
        fy = np.polyfit(H, [o["cy"] for o in dol], 1)
        nach = float(np.clip(np.polyfit(H, R, 1)[0], -0.015, 0.0))
    else:
        fx = [0, dol[0]["cx"]]; fy = [0, dol[0]["cy"]]; nach = -0.005
    h0 = ok[0]["h"]
    r0 = float(np.median(R[:5]))
    nowe = []
    hc = h0 - P.PIEN_KROK
    while hc >= P.MIN_WYSOKOSC - 1e-6:
        nowe.append(dict(h=round(hc, 3), cx=float(np.polyval(fx, hc)),
                         cy=float(np.polyval(fy, hc)),
                         r=r0 + nach * (hc - h0), n=0, blad=np.nan,
                         pokrycie=0.0, rekonstrukcja=True))
        hc -= P.PIEN_KROK
    return nowe[::-1]


def kontrola_dolu(ok):
    """
    Dol pnia (0.9-2.5 m) musi pasowac do zbieznosci czystej czesci
    (2.5-8 m). Okregi grubsze o ponad 35% od przewidywanych to zwykle krzak
    zlepiony z pniem - wyrzucamy je, a ten kawalek zostanie dorysowany.
    """
    H = np.array([o["h"] for o in ok]); R = np.array([o["r"] for o in ok])
    czysty = (H >= 2.5) & (H <= 8.0)
    if czysty.sum() < 5:
        return ok
    f = np.polyfit(H[czysty], R[czysty], 1)
    f[0] = min(f[0], 0.0)                     # w dol pien nie moze chudnac
    przew = np.polyval(f, H)
    # tylko ZA GRUBE: krzak zlepiony z pniem pogrubia go; zgrubienie
    # odziomkowe jest naturalne, wiec dopuszczamy +35%
    zle = (H < 2.5) & (H > 0.9) & (R > przew * 1.35)
    if not zle.any():
        return ok
    granica = H[zle].max()
    return [o for o in ok if o["h"] > granica]


def dopelnij_dol(ok, wszystkie):
    """
    Gdy wybrany lancuch nie schodzi do ziemi, zagladamy do okregow z innych
    prob (np. sledzenia od 1 m w gore). Bierzemy te, ktore leza na
    przedluzeniu osi i maja promien zgodny ze zbieznoscia. To ZMIERZONY pien,
    wiec lepszy niz dorysowany.
    """
    h0 = ok[0]["h"]
    if h0 <= P.MIN_WYSOKOSC + P.PIEN_KROK * 1.5:
        return ok
    model = {round(o["h"], 2): o for o in rekonstruuj_dol(ok)}
    dobre = {}
    for o in wszystkie:
        if o["h"] >= h0 - 1e-6 or o.get("rekonstrukcja"):
            continue
        m = model.get(round(o["h"], 2))
        if m is None or o["pokrycie"] < 120:
            continue
        if (np.hypot(o["cx"] - m["cx"], o["cy"] - m["cy"]) < 0.10 and
                0.85 <= o["r"] / m["r"] <= 1.35):
            k = round(o["h"], 2)
            if k not in dobre or o["n"] > dobre[k]["n"]:
                dobre[k] = dict(o, rekonstrukcja=False)
    return sorted(list(dobre.values()) + ok, key=lambda o: o["h"])


def sledz_pien(xyz, h, rng):
    """
    Szuka pnia na KILKU wysokosciach (1 m, 2 m, 3 m ... az do 6.5 m) i z kazdego
    miejsca sledzi go w gore i w dol. Wygrywa najdluzszy spojny lancuch.

    Dlaczego nie tylko od dolu: w gestym podszyciu na 1 m stoi krzak, ktory
    potrafi udawac pien o srednicy metra. Wyzej, ponad podszytem, pien jest
    czysty - i stamtad idziemy w dol, ostroznie. Gdy w dol sie nie da,
    brakujacy kawalek DORYSOWUJEMY (rekonstrukcja) i oznaczamy jako szacowany.
    """
    wys = float(np.percentile(h, 99.5))
    najlepszy, ocena = [], 0
    wszystkie = []                       # okregi ze wszystkich prob - zapas
    for dol in P.PIEN_WYSOKOSCI_STARTU:
        if dol > max(1.0, 0.6 * wys):
            continue
        for start in znajdz_start(xyz, h, rng, dol):
            gora = idz(start, xyz, h, rng, +1)
            czysty = [start] + gora
            r_wz = float(np.median([o["r"] for o in czysty]))
            dol_ = idz(start, xyz, h, rng, -1, r_wzor=r_wz)
            lanc = sorted(dol_ + czysty, key=lambda o: o["h"])
            wszystkie.extend(lanc)
            oc = ocena_lancucha(lanc)
            if oc > ocena:
                najlepszy, ocena = lanc, oc
        if ocena >= 25:          # >= 5 m spojnego pnia - wystarczy szukac
            break
    if len(najlepszy) < 3:
        return []
    for o in najlepszy:
        o.setdefault("rekonstrukcja", False)
    najlepszy = kontrola_dolu(najlepszy)
    najlepszy = dopelnij_dol(najlepszy, wszystkie)
    if najlepszy[0]["h"] > P.MIN_WYSOKOSC + P.PIEN_KROK * 1.5:
        najlepszy = rekonstruuj_dol(najlepszy) + najlepszy
    return najlepszy


# ======================================================================
# ZROSNIETE DRZEWA - dwa pnie w jednym drzewie z etapu 1
# ======================================================================
# Segmentacja z etapu 1 czasem skleja dwa drzewa, gdy pnie stoją tuż obok
# siebie albo zrosły się u dołu. Szukamy wtedy w tym samym „drzewie”
# drugiego pnia: po zdjęciu punktów pnia głównego śledzimy pień jeszcze
# raz. Drugi pień musi być długi, prosty, okrągły i leżeć OBOK pnia
# głównego (nie na nim). Reguła leśna: rozwidlenie poniżej 1,3 m to dwa
# drzewa, wyżej - jedno drzewo z rozwidleniem.
ROZDZIEL_MIN_DL_M = 4.0        # zmierzony drugi pień co najmniej tyle
ROZDZIEL_UDZIAL_WYS = 0.4      # i co najmniej taka część wysokości drzewa
                               # (gęste okółki świerka dają krótkie
                               # „pnie” z gałęzi - prawdziwy drugi pień
                               # sięga wysoko)
ROZDZIEL_MIN_D_M = 0.10        # i co najmniej taka średnica
ROZDZIEL_MAX_POCHYLENIE = 20.0  # stopni od pionu (gałąź jest bardziej skośna)
ROZDZIEL_MIN_POKRYCIE = 150.0  # mediana łuku okręgów drugiego pnia
ROZDZIEL_OBOK = 0.8            # tyle okręgów musi leżeć obok pnia głównego
ROZDZIEL_DO_M = 1.8            # drugi pień widoczny osobno już tak nisko
ROZDZIEL_DALEKO_M = 0.50       # albo od początku tak daleko od głównego
ROZDZIEL_LUK_13 = 60.0         # albo na 1,3 m widać łuk jego kory (stopnie)
ROZDZIEL_MAX_PNI = 3           # najwyżej tyle pni w jednym drzewie
ROZDZIEL_PROB = 3              # tyle prób śledzenia na drzewo


def _os(okregi):
    H = np.array([o["h"] for o in okregi])
    X = np.array([o["cx"] for o in okregi])
    Y = np.array([o["cy"] for o in okregi])
    R = np.array([o["r"] for o in okregi])
    return H, X, Y, R


def _os_w(os_, hh):
    """Środek i promień pnia na wysokościach hh; poza zmierzonym odcinkiem
    prosta dopasowana do górnej (wyżej) albo dolnej (niżej) połowy osi."""
    H, X, Y, R = os_
    cx, cy, r = np.interp(hh, H, X), np.interp(hh, H, Y), np.interp(hh, H, R)
    pol = max(2, len(H) // 2)
    dol = max(2, int((H < H.min() + 3.0).sum()))   # w dół: dolne 3 m osi
    for m, sl in ((hh > H.max(), slice(-pol, None)),
                  (hh < H.min(), slice(None, dol))):
        if m.any() and len(H) >= 2:
            fx = np.polyfit(H[sl], X[sl], 1)
            fy = np.polyfit(H[sl], Y[sl], 1)
            cx[m], cy[m] = np.polyval(fx, hh[m]), np.polyval(fy, hh[m])
    return cx, cy, r


def drugi_pien(p, hh, rng):
    """Szuka drugiego pnia w punktach jednego drzewa. Zwraca
    (os_glowna, os_druga, opis) gdy drugi pień to osobne drzewo,
    (None, None, opis rozwidlenia) gdy to rozwidlenie powyżej 1,3 m,
    albo (None, None, None)."""
    A = sledz_pien(p, hh, rng)
    if len(A) < 3:
        return None, None, None
    osA = _os(A)
    cx, cy, r = _os_w(osA, hh)
    reszta = (np.hypot(p[:, 0] - cx, p[:, 1] - cy) - r > 0.03) | \
        (hh > osA[0].max() + 0.3)
    if reszta.sum() < 200:
        return None, None, None
    B = [o for o in sledz_pien(p[reszta], hh[reszta], rng)
         if not o.get("rekonstrukcja")]
    if len(B) < 5:
        return None, None, None
    osB = _os(B)
    Hb, Xb, Yb, Rb = osB
    dl = Hb.max() - Hb.min()
    poch = np.degrees(np.arctan2(np.hypot(Xb[-1] - Xb[0], Yb[-1] - Yb[0]),
                                 max(dl, 0.1)))
    ax, ay, ar = _os_w(osA, Hb)
    odst = np.hypot(Xb - ax, Yb - ay) - Rb - ar      # przerwa między korami
    pokr = float(np.median([o["pokrycie"] for o in B]))
    wys = float(np.percentile(hh, 99.5))
    if not (dl >= max(ROZDZIEL_MIN_DL_M, ROZDZIEL_UDZIAL_WYS * wys)
            and 2 * np.median(Rb) >= ROZDZIEL_MIN_D_M
            and poch <= ROZDZIEL_MAX_POCHYLENIE
            and pokr >= ROZDZIEL_MIN_POKRYCIE
            and (odst > 0.02).mean() >= ROZDZIEL_OBOK):
        return None, None, None
    opis = dict(od_m=round(float(Hb.min()), 1), do_m=round(float(Hb.max()), 1),
                srednica_cm=round(float(2 * np.median(Rb) * 100), 0),
                odstep_m=round(float(np.median(odst)), 2),
                pochylenie_deg=round(float(poch), 0))
    # drugi pień widać osobno na 1,3 m? (łuk kory obok pnia głównego -
    # oś drugiego pnia przedłużona w dół prostą z jego dolnej części)
    m13 = np.abs(hh - 1.3) <= 0.1
    luk = 0.0
    if m13.any():
        bx, by, br = _os_w(osB, hh[m13])
        ax13, ay13, ar13 = _os_w(osA, hh[m13])
        q = p[m13]
        naB = (np.abs(np.hypot(q[:, 0] - bx, q[:, 1] - by) - br) < 0.04) & \
            (np.hypot(q[:, 0] - ax13, q[:, 1] - ay13) - ar13 > 0.02)
        if naB.sum() >= 15:
            luk = pokrycie_katowe(q[naB, 0], q[naB, 1], bx[0], by[0])
    opis["luk_13_deg"] = round(float(luk), 0)
    if Hb.min() <= ROZDZIEL_DO_M or luk >= ROZDZIEL_LUK_13 or \
            float(np.median(odst[:3])) >= ROZDZIEL_DALEKO_M:
        return osA, osB, opis
    return None, None, opis                     # rozwidlenie wyżej


def rozdziel_zrosniete(xyz, h, drzewo, pozycje=None):
    """Rozdziela drzewa z dwoma (albo trzema) pniami. Zwraca nowe numery
    drzew i tabelę: stare, nowe, opis (pusta, gdy nic nie rozdzielono).
    pozycje: {nr: (x, y)} pni z etapu 1 - stary numer zostaje przy pniu,
    który tam stoi (do niego należy pierśnica z etapu 1)."""
    pozycje = pozycje or {}
    print(J.t("\n[PNIE ZROŚNIĘTE] Szukam drugiego pnia w każdym drzewie",
              "\n[MERGED STEMS] Looking for a second stem in every tree"),
          flush=True)
    t0 = time.time()
    drzewo = drzewo.copy()
    nowy = int(drzewo.max()) + 1
    wiersze = []
    kolej = np.argsort(drzewo, kind="stable")
    ds = drzewo[kolej]
    granice = np.flatnonzero(np.r_[True, ds[1:] != ds[:-1], True])
    for a, b in zip(granice[:-1], granice[1:]):
        t = int(ds[a])
        if t <= 0 or b - a < 2000:
            continue
        idx = kolej[a:b]
        for _ in range(ROZDZIEL_MAX_PNI - 1):
            p, hh = xyz[idx], h[idx]
            # śledzenie ma element losowy (RANSAC) - kilka prób z ziarnem
            # zależnym od numeru drzewa: wynik powtarzalny, mniej pomyłek
            osA = osB = opis = None
            for proba in range(ROZDZIEL_PROB):
                rng = np.random.default_rng(t * 7919 + proba + len(idx) % 97)
                a_, b_, o_ = drugi_pien(p, hh, rng)
                if a_ is not None:
                    osA, osB, opis = a_, b_, o_
                    break
                if o_ is not None and opis is None:
                    opis = o_
            if opis is None:
                break
            if osA is None:
                wiersze.append(dict(drzewo=t, nowe=np.nan,
                                    rodzaj="rozwidlenie", **opis))
                break
            # każdy punkt do bliższego pnia (odległość od kory w poziomie)
            ax, ay, ar = _os_w(osA, hh)
            bx, by, br = _os_w(osB, hh)
            dA = np.hypot(p[:, 0] - ax, p[:, 1] - ay) - ar
            dB = np.hypot(p[:, 0] - bx, p[:, 1] - by) - br
            doB = dB < dA
            # stary numer zostaje przy pniu, który stoi w miejscu drzewa z
            # etapu 1 (do niego należy tamta pierśnica); bez pozycji - przy
            # grubszym
            if t in pozycje:
                h13 = np.array([1.3])
                ax1, ay1, _ = _os_w(osA, h13)
                bx1, by1, _ = _os_w(osB, h13)
                px, py = pozycje[t]
                zamien = np.hypot(bx1[0] - px, by1[0] - py) < \
                    np.hypot(ax1[0] - px, ay1[0] - py)
            else:
                zamien = np.median(osB[3][:5]) > \
                    np.median(osA[3][osA[0] >= 0.8][:5])
            if zamien:
                doB = ~doB
                opis["srednica_cm"] = round(float(2 * np.median(
                    osA[3][osA[0] >= 0.8][:5]) * 100), 0)
            if doB.sum() < 500 or (~doB).sum() < 500:
                break
            drzewo[idx[doB]] = nowy
            wiersze.append(dict(drzewo=t, nowe=nowy, rodzaj="rozdzielone",
                                **opis))
            print(J.t(f"         drzewo {t}: drugi pień {opis['srednica_cm']:.0f}"
                      f" cm ({opis['od_m']:g}-{opis['do_m']:g} m) -> nowe "
                      f"drzewo {nowy}",
                      f"         tree {t}: second stem {opis['srednica_cm']:.0f}"
                      f" cm ({opis['od_m']:g}-{opis['do_m']:g} m) -> new "
                      f"tree {nowy}"), flush=True)
            nowy += 1
            idx = idx[~doB]
    tab = pd.DataFrame(wiersze, columns=["drzewo", "nowe", "rodzaj", "od_m",
                                         "do_m", "srednica_cm", "odstep_m",
                                         "pochylenie_deg", "luk_13_deg"])
    n_r = int((tab.rodzaj == "rozdzielone").sum()) if len(tab) else 0
    n_w = int((tab.rodzaj == "rozwidlenie").sum()) if len(tab) else 0
    print(J.t(f"         rozdzielone: {n_r}, rozwidlenia powyżej 1,3 m "
              f"(jedno drzewo): {n_w}   ({time.time() - t0:.0f} s)",
              f"         split: {n_r}, forks above 1.3 m (one tree): "
              f"{n_w}   ({time.time() - t0:.0f} s)"), flush=True)
    return drzewo, tab


def krok2_pnie(xyz, drzewo, h):
    print(J.t(f"\n[KROK 2] Sledze pnie (plaster {P.PIEN_KROK} m, start na "
            f"kilku wysokosciach, dorysowanie zaslonietego dolu)",
            f"\n[STEP 2] Tracing stems (slice {P.PIEN_KROK} m, start at "
            f"several heights, reconstruction of hidden stem base)"))
    t0 = time.time()
    rng = np.random.default_rng(0)
    jest_pniem = np.zeros(len(xyz), bool)
    wiersze, okregi_csv = [], []

    kolej = np.argsort(drzewo, kind="stable")
    ds = drzewo[kolej]
    granice = np.flatnonzero(np.r_[True, ds[1:] != ds[:-1], True])
    for a, b in zip(granice[:-1], granice[1:]):
        t = int(ds[a])
        if t <= 0:
            continue
        idx = kolej[a:b]
        p, hh = xyz[idx], h[idx]
        ok = sledz_pien(p, hh, rng)
        zm = [o for o in ok if not o["rekonstrukcja"]]
        wiersz = dict(treeID=t, liczba_punktow=len(idx),
                      wysokosc_drzewa_m=round(float(np.percentile(hh, 99.9)), 2),
                      pien_okregow=len(zm))
        if len(zm) >= 3:
            H = np.array([o["h"] for o in ok])
            CX = np.array([o["cx"] for o in ok])
            CY = np.array([o["cy"] for o in ok])
            R = np.array([o["r"] for o in ok])
            rek = np.array([o["rekonstrukcja"] for o in ok])
            # wygladzenie promienia - pojedyncze okregi bywaja zawyzone
            Rg = R.copy()
            Rg[~rek] = pd.Series(R[~rek]).rolling(5, center=True,
                                                 min_periods=1).median().to_numpy()
            # punkty pnia tylko tam, gdzie pien ZMIERZONO
            Hz = H[~rek]
            dol, gora = Hz.min() - P.PIEN_KROK / 2, Hz.max() + P.PIEN_KROK / 2
            w = (hh >= dol) & (hh <= gora)
            cx = np.interp(hh[w], H, CX); cy = np.interp(hh[w], H, CY)
            rr = np.interp(hh[w], H, Rg)
            d = np.hypot(p[w, 0] - cx, p[w, 1] - cy)
            jest_pniem[idx[w][d <= rr + P.PIEN_TOLERANCJA]] = True
            if H.min() <= 1.3 <= H.max():
                d13 = 2 * float(np.interp(1.3, H, Rg))
                zrodlo = "rekonstrukcja" if 1.3 < Hz.min() - P.PIEN_KROK / 2 \
                    else "pomiar"
            else:
                d13, zrodlo = np.nan, "brak"
            i13 = int(np.argmin(abs(H - 1.3)))
            wiersz.update(pien_od_m=round(float(dol), 2),
                          pien_do_m=round(float(gora), 2),
                          dorysowano_od_m=round(float(H[rek].min()), 2) if rek.any() else np.nan,
                          dorysowano_do_m=round(float(dol), 2) if rek.any() else np.nan,
                          srednica_13_m=round(d13, 4) if d13 == d13 else np.nan,
                          srednica_13_zrodlo=zrodlo,
                          srednica_u_gory_m=round(float(2 * np.median(R[~rek][-3:])), 4),
                          pozycja_x=round(float(CX[i13]), 3),
                          pozycja_y=round(float(CY[i13]), 3))
            for o, rg in zip(ok, Rg):
                okregi_csv.append(dict(treeID=t, wysokosc_m=round(o["h"], 2),
                                       srodek_x=round(o["cx"], 4),
                                       srodek_y=round(o["cy"], 4),
                                       srednica_m=round(2 * o["r"], 4),
                                       srednica_wygladzona_m=round(2 * rg, 4),
                                       blad_m=round(o["blad"], 4) if o["blad"] == o["blad"] else np.nan,
                                       pokrycie_deg=o["pokrycie"],
                                       punktow=o["n"],
                                       zrodlo="rekonstrukcja" if o["rekonstrukcja"] else "pomiar"))
        wiersze.append(wiersz)

    tab = pd.DataFrame(wiersze)
    z_pniem = int((tab.pien_okregow >= 3).sum())
    n_rek = int(tab.get("dorysowano_od_m", pd.Series(dtype=float)).notna().sum())
    print(J.t(f"         pien znaleziony w {z_pniem} z {len(tab)} drzew "
            f"(w {n_rek} dorysowany zasloniety dol), punktow pnia: "
            f"{jest_pniem.sum():,}   ({time.time()-t0:.0f} s)",
            f"         stem found in {z_pniem} of {len(tab)} trees "
            f"(hidden base reconstructed in {n_rek}), stem points: "
            f"{jest_pniem.sum():,}   ({time.time()-t0:.0f} s)"))
    return jest_pniem, tab, pd.DataFrame(okregi_csv)


# ======================================================================
# KROK 3 - CECHY
# ======================================================================
def cechy_pca(pkt, k):
    """
    Dla kazdego punktu: rozklad sasiedztwa na trzy kierunki glowne
    (wartosci wlasne l1 >= l2 >= l3). Z nich:
        liniowosc     (l1-l2)/l1   ~1 na galezi
        plaskosc      (l2-l3)/l1   ~1 na powierzchni (kora grubego pnia)
        rozproszenie   l3/l1       ~1 w kepie lisci
        pionowosc      |skladowa z kierunku glownego|
    """
    kd = cKDTree(pkt)
    n = len(pkt)
    out = np.zeros((n, 5), np.float32)
    for a in range(0, n, 200_000):
        b = min(n, a + 200_000)
        odl, sas = kd.query(pkt[a:b], k=k, workers=-1)
        q = pkt[sas]                                  # (m, k, 3)
        q = q - q.mean(axis=1, keepdims=True)
        cov = np.einsum("mki,mkj->mij", q, q) / k
        wart, wekt = np.linalg.eigh(cov)              # rosnaco
        l3, l2, l1 = [np.maximum(wart[:, i], 1e-12) for i in range(3)]
        out[a:b, 0] = (l1 - l2) / l1
        out[a:b, 1] = (l2 - l3) / l1
        out[a:b, 2] = l3 / l1
        out[a:b, 3] = np.abs(wekt[:, 2, 2])           # z kierunku glownego
        out[a:b, 4] = odl[:, -1]                      # gestosc (promien k)
    return out


def krok3_cechy(xyz, drzewo, h, jest_pniem, tab_pni):
    print(J.t(f"\n[KROK 3] Cechy geometryczne (voxel {P.VOXEL_CECH} m)",
            f"\n[STEP 3] Geometric features (voxel {P.VOXEL_CECH} m)"))
    t0 = time.time()
    uzyte = (drzewo > 0) & (h >= P.MIN_WYSOKOSC)
    idx_uz = np.flatnonzero(uzyte)
    p = xyz[idx_uz]
    kl = np.floor((p - p.min(axis=0)) / P.VOXEL_CECH).astype(np.int64)
    klucz = (kl[:, 0] << 42) | (kl[:, 1] << 21) | kl[:, 2]
    _, pierwszy, odwr = np.unique(klucz, return_index=True, return_inverse=True)
    odwr = odwr.ravel()
    nv = len(pierwszy)
    licz = np.bincount(odwr, minlength=nv).astype(float)
    vox = np.column_stack([np.bincount(odwr, weights=p[:, i], minlength=nv) / licz
                           for i in range(3)])
    print(J.t(f"         voxeli: {nv:,} (z {len(p):,} punktow)",
            f"         voxels: {nv:,} (from {len(p):,} points)"))

    c1 = cechy_pca(vox, P.SASIEDZI_MALA_SKALA)
    c2 = cechy_pca(vox, P.SASIEDZI_DUZA_SKALA)

    # udzial punktow pnia w voxelu i drzewo voxela (najczestsze)
    pien_v = np.bincount(odwr, weights=jest_pniem[idx_uz].astype(float),
                         minlength=nv) / licz
    drzewo_v = drzewo[idx_uz][pierwszy]
    h_v = np.bincount(odwr, weights=h[idx_uz], minlength=nv) / licz

    # odleglosc w poziomie od osi pnia (srodek na 1.3 m albo srodek drzewa)
    poz = {}
    for r in tab_pni.itertuples():
        if hasattr(r, "pozycja_x") and r.pozycja_x == r.pozycja_x:
            poz[r.treeID] = (r.pozycja_x, r.pozycja_y)
    sx = np.full(nv, np.nan); sy = np.full(nv, np.nan)
    for t in np.unique(drzewo_v):
        m = drzewo_v == t
        if t in poz:
            sx[m], sy[m] = poz[t]
        else:
            sx[m], sy[m] = np.median(vox[m, 0]), np.median(vox[m, 1])
    odl_pien = np.hypot(vox[:, 0] - sx, vox[:, 1] - sy)
    wys_drz = tab_pni.set_index("treeID")["wysokosc_drzewa_m"]
    h_wzgl = h_v / np.maximum(wys_drz.reindex(drzewo_v).to_numpy(), 1.0)

    X = np.column_stack([c1, c2, h_wzgl, odl_pien]).astype(np.float32)
    print(f"         ({time.time()-t0:.0f} s)")
    return dict(idx_uz=idx_uz, odwr=odwr, vox=vox, X=X, c1=c1, c2=c2,
                pien_v=pien_v, odl_pien=odl_pien, drzewo_v=drzewo_v)


# ======================================================================
# KROK 4 - SAMOUCZENIE
# ======================================================================
def krok4_drewno_lisc(V):
    print(J.t("\n[KROK 4] Samouczenie drewno / lisc",
            "\n[STEP 4] Self-training wood / leaf"))
    t0 = time.time()
    c1, c2, X = V["c1"], V["c2"], V["X"]
    pien = V["pien_v"] > 0.5
    galaz = (~pien & (c1[:, 0] > P.GALAZ_MIN_LINIOWOSC) &
             (c2[:, 0] > P.GALAZ_MIN_LINIOWOSC) &
             (c1[:, 2] < P.GALAZ_MAX_ROZPROSZENIE))
    lisc = (~pien & (c1[:, 2] > P.LISC_MIN_ROZPROSZENIE) &
            (c2[:, 0] < P.LISC_MAX_LINIOWOSC) &
            (V["odl_pien"] > P.LISC_MIN_ODL_OD_PNIA))
    print(J.t(f"         pewne przyklady: pien {pien.sum():,}, galezie "
            f"{galaz.sum():,}, liscie {lisc.sum():,}",
            f"         confident examples: stem {pien.sum():,}, branches "
            f"{galaz.sum():,}, leaves {lisc.sum():,}"))

    rng = np.random.default_rng(1)
    def probka(m, n):
        i = np.flatnonzero(m)
        return i if len(i) <= n else rng.choice(i, n, replace=False)
    pol = P.MAX_PRZYKLADOW_NA_KLASE // 2
    i_dr = np.r_[probka(pien, pol), probka(galaz, pol)]
    i_li = probka(lisc, P.MAX_PRZYKLADOW_NA_KLASE)
    if len(i_li) < 500 or len(i_dr) < 500:
        print(J.t("         UWAGA: za malo pewnych przykladow jednej z klas - "
                "uzywam samych regul",
                "         WARNING: too few confident examples of one class "
                "- using rules only"))
        p = np.where(pien | galaz, 1.0, np.where(lisc, 0.0, 0.5))
        return p.astype(np.float32)
    # Cechy "odleglosc od pnia" i "wysokosc" nie ida do modelu: pewne
    # przyklady drewna to glownie pien, wiec model nauczylby sie
    # "blisko osi = drewno" i nie rozpoznal galezi w koronie.
    kol = list(range(10))
    Xt = X[np.r_[i_dr, i_li]][:, kol]
    yt = np.r_[np.ones(len(i_dr)), np.zeros(len(i_li))]
    rf = RandomForestClassifier(n_estimators=80, max_depth=14,
                                min_samples_leaf=20, n_jobs=-1,
                                class_weight="balanced", random_state=0)
    rf.fit(Xt, yt)
    p = rf.predict_proba(X[:, kol])[:, 1].astype(np.float32)
    p[pien] = 1.0
    print(J.t(f"         drewno (p > {P.PROG_DREWNA}): "
            f"{(p > P.PROG_DREWNA).mean()*100:.1f}% voxeli   "
            f"({time.time()-t0:.0f} s)",
            f"         wood (p > {P.PROG_DREWNA}): "
            f"{(p > P.PROG_DREWNA).mean()*100:.1f}% of voxels   "
            f"({time.time()-t0:.0f} s)"))
    return p


# ======================================================================
# KROK 5 - SPRZATANIE
# ======================================================================
def krok5_sprzatanie(V, p):
    print(J.t("\n[KROK 5] Sprzatanie malych kawalkow drewna w koronie",
            "\n[STEP 5] Cleaning up small pieces of wood in the crown"))
    pien = V["pien_v"] > 0.5
    drewno = (p > P.PROG_DREWNA) & ~pien
    klasa = np.where(pien, PIEN, np.where(drewno, GALEZ, LISC)).astype(np.uint8)

    i_dr = np.flatnonzero(drewno | pien)
    if len(i_dr) == 0:
        return klasa
    kd = cKDTree(V["vox"][i_dr])
    pary = kd.query_pairs(P.VOXEL_CECH * 2.5, output_type="ndarray")
    # nie lacz voxeli roznych drzew
    pary = pary[V["drzewo_v"][i_dr[pary[:, 0]]] ==
                V["drzewo_v"][i_dr[pary[:, 1]]]]
    g = coo_matrix((np.ones(len(pary)), (pary[:, 0], pary[:, 1])),
                   shape=(len(i_dr), len(i_dr)))
    _, et = connected_components(g, directed=False)
    rozm = np.bincount(et)
    z_pniem = np.zeros(len(rozm), bool)
    z_pniem[np.unique(et[pien[i_dr]])] = True
    zle = ~z_pniem[et] & (rozm[et] < P.MIN_VOXELI_GALEZI)
    klasa[i_dr[zle]] = LISC
    print(J.t(f"         przeniesiono do ulistnienia: {zle.sum():,} voxeli",
            f"         moved to foliage: {zle.sum():,} voxels"))
    return klasa


# ======================================================================
# KROK 6 - ZAPIS
# ======================================================================
# ======================================================================
# GRUPA GATUNKOWA (iglaste / liściaste) - reguły z kształtu drzewa
# ======================================================================
# Bez uczenia, same reguły, wiec to jest WSTEPNA ocena. Glosuja cztery
# cechy (waga w nawiasie):
#   - dominacja wierzchołkowa (0.50): do jakiej czesci wysokosci da sie
#     sledzic jeden pien. Iglaste maja pien do wierzcholka, liściaste
#     zwykle rozwidlaja sie w koronie.
#   - szczyt korony (0.20): promien korony w gornych 15% wysokosci
#     wzgledem najszerszego miejsca. Stożek (świerk, jodła) ma ostry
#     szczyt, liściaste zaokraglony.
#   - srodek ciezkosci korony (0.15): stożek jest najszerszy u dołu.
#   - szerokosc / dlugosc korony (0.15): liściaste maja korone szersza.
# Sosna z płaską koroną potrafi wyjsc "nieokreslona" - wtedy wpisz grupe
# recznie w <skan>_gatunki.csv (raport ja uwzgledni).
GRUPA_MIN_WYSOKOSC = 8.0     # nizsze drzewa (podrost, krzewy) - bez oceny
GRUPA_PROG = 0.25            # |wynik| ponizej progu -> nieokreslone
# W lasach, które mierzymy, główne gatunki to świerk i buk, więc grupa
# iglasta to domyślnie świerk, a liściasta buk. Inny gatunek wpisz ręcznie
# w <skan>_gatunki.csv.
GATUNEK_GRUPY = {"iglaste": "świerk", "liściaste": "buk",
                 "nieokreślone": "nieokreślony"}


def profil_korony(p, hh, okr_t, warstwa=0.5):
    """Promien korony (90. percentyl odleglosci od osi pnia) w warstwach."""
    H = np.percentile(hh, 99.5)
    if okr_t is not None and len(okr_t):
        o = okr_t.sort_values("wysokosc_m")
        cx = np.interp(hh, o.wysokosc_m, o.srodek_x)
        cy = np.interp(hh, o.wysokosc_m, o.srodek_y)
    else:
        g = hh > 1.0
        cx = np.median(p[g, 0]) if g.any() else p[:, 0].mean()
        cy = np.median(p[g, 1]) if g.any() else p[:, 1].mean()
    d = np.hypot(p[:, 0] - cx, p[:, 1] - cy)
    zb = np.arange(1.3, H, warstwa)
    r = np.zeros(len(zb))
    for i, z in enumerate(zb):
        m = (hh >= z) & (hh < z + warstwa)
        if m.sum() >= 15:
            r[i] = np.percentile(d[m], 90)
    return zb + warstwa / 2, r, H


def cechy_korony(p, hh, okr_t, pien_do):
    z, r, H = profil_korony(p, hh, okr_t)
    if H < GRUPA_MIN_WYSOKOSC or len(z) < 6 or r.max() <= 0:
        return None
    rs = np.convolve(r, np.ones(3) / 3, mode="same")
    rmax = rs.max()
    # podstawa korony: nad ostatnia "waska" warstwa (sam pien) ponizej
    # najszerszego miejsca. Podszyt przy gruncie jest szeroki, ale miedzy
    # nim a korona zwykle jest odcinek gołego pnia.
    imax = int(np.argmax(rs))
    waskie = np.flatnonzero(rs[:imax] < 0.35 * rmax)
    hk = z[waskie[-1] + 1] if len(waskie) else z[0]
    kor = z >= hk
    Lk = max(H - hk, 0.5)
    zc = float(np.sum(rs[kor] ** 2 * (z[kor] - hk)) / np.sum(rs[kor] ** 2)
               / Lk)
    gora = z >= 0.85 * H
    szczyt = float(rs[gora].mean() / rmax) if gora.any() else 0.6
    dom = pien_do / H if np.isfinite(pien_do) else 0.65
    return dict(H=H, hk=hk, Lk=Lk, zc=zc, szczyt=szczyt,
                sdl=2 * rmax / Lk, dom=dom)


def rozpoznaj_grupe(xyz, h, drzewo, tab, okregi):
    kolejnosc = np.argsort(drzewo, kind="stable")
    granice = np.searchsorted(drzewo[kolejnosc], tab.treeID.to_numpy())
    konce = np.searchsorted(drzewo[kolejnosc], tab.treeID.to_numpy(), "right")
    wynik = []
    for t, a, b, pd_ in zip(tab.treeID, granice, konce, tab.pien_do_m):
        idx = kolejnosc[a:b]
        okr_t = okregi[okregi.treeID == t] if len(okregi) else None
        c = cechy_korony(xyz[idx], h[idx], okr_t, pd_) if len(idx) else None
        if c is None:
            wynik.append(("nieokreślone", np.nan, np.nan, np.nan))
            continue
        clip = lambda x: float(np.clip(x, -1, 1))
        w = (0.50 * clip((c["dom"] - 0.65) / 0.20) +
             0.20 * clip((0.60 - c["szczyt"]) / 0.25) +
             0.15 * clip((0.50 - c["zc"]) / 0.15) +
             0.15 * clip((0.70 - c["sdl"]) / 0.40))
        gr = ("iglaste" if w >= GRUPA_PROG else
              "liściaste" if w <= -GRUPA_PROG else "nieokreślone")
        wynik.append((gr, round(min(abs(w), 1.0) * 100),
                      round(c["hk"], 1), round(c["Lk"] / c["H"] * 100)))
    w = pd.DataFrame(wynik, columns=["grupa_gatunkowa", "grupa_pewnosc_proc",
                                     "podstawa_korony_m", "dl_korony_proc"])
    w.insert(0, "gatunek", w.grupa_gatunkowa.map(GATUNEK_GRUPY))
    tab = pd.concat([tab.reset_index(drop=True), w], axis=1)
    n = tab.grupa_gatunkowa.value_counts()
    print(J.t("         grupa gatunkowa (wstepnie): ",
            "         species group (preliminary): ") +
          ", ".join(f"{J.gatunek(k)} {n.get(k, 0)}" for k in
                    ("iglaste", "liściaste", "nieokreślone")), flush=True)
    return tab


# ======================================================================
# KONTROLA PNIA - czy to drzewo, czy krzew
# ======================================================================
# Prawdziwy pien jest PUSTY W SRODKU: skaner widzi tylko kore, wiec punkty
# przekroju leza na okregu (albo na jego widocznym luku - nie trzeba
# pokrycia dookola), a nie wewnatrz. Krzew i gesty mlody swierk maja punkty
# w calym przekroju. Sprawdzamy to na 1,3 m i na 3 m (na 3 m podszyt juz
# zwykle nie przeszkadza):
#   wnetrze = udzial punktow blizej srodka niz 0,7 promienia
#             wsrod punktow lezacych w okregu (+3 cm).
# Na S2j: prawdziwe pnie 0-0,02, krzewy 0,2-0,5.
KONTROLA_PUSTY = 0.15        # wnetrze ponizej -> pien potwierdzony
KONTROLA_PELNY = 0.20        # wnetrze od tego -> punkty w srodku
KONTROLA_NISKIE = 10.0       # nizsze drzewa bez potwierdzonego pnia = krzew
KONTROLA_MIN_PUNKTOW = 15    # mniej punktow przy okregu = nie da sie ocenic
PIERSNICA_MIN_PUNKTOW = 40   # tyle punktow musi miec okrag na 1,3 m ...
PIERSNICA_MIN_POKRYCIE = 150.0   # ... i tyle stopni luku, zeby mu ufac


def wnetrze_przekroju(p, hh, okr_t, z, pas=0.10):
    """(wnetrze, punktow, okrag) dla przekroju na wysokosci z."""
    if okr_t is None or len(okr_t) == 0:
        return np.nan, 0, None
    o = okr_t.iloc[(okr_t.wysokosc_m - z).abs().argsort()[:1]].iloc[0]
    if abs(o.wysokosc_m - z) > 0.3:
        return np.nan, 0, None
    r = o.srednica_m / 2
    m = np.abs(hh - z) <= pas
    d = np.hypot(p[m, 0] - o.srodek_x, p[m, 1] - o.srodek_y)
    blisko = d <= r + 0.03
    n = int(blisko.sum())
    if n < KONTROLA_MIN_PUNKTOW:
        return np.nan, n, o
    return float((d[blisko] < 0.7 * r).sum() / n), n, o


def kontrola_pnia(xyz, h, drzewo, tab, okregi, niskie=None):
    niskie = KONTROLA_NISKIE if niskie is None else niskie
    kolejnosc = np.argsort(drzewo, kind="stable")
    ds = drzewo[kolejnosc]
    pomiar = okregi[okregi.zrodlo == "pomiar"] if len(okregi) else okregi
    gr = dict(tuple(pomiar.groupby("treeID"))) if len(pomiar) else {}
    wyn = []
    d_x = tab.srednica_13_m.to_numpy(float) if "srednica_13_m" in tab \
        else np.full(len(tab), np.nan)
    for t, wys, dx in zip(tab.treeID, tab.wysokosc_drzewa_m, d_x):
        idx = kolejnosc[np.searchsorted(ds, t):np.searchsorted(ds, t, "right")]
        okr_t = gr.get(t)
        w13, n13, o13 = wnetrze_przekroju(xyz[idx], h[idx], okr_t, 1.3)
        w3, n3, _ = wnetrze_przekroju(xyz[idx], h[idx], okr_t, 3.0)
        pusty = (w13 < KONTROLA_PUSTY) or (w3 < KONTROLA_PUSTY)
        pelny = (w13 >= KONTROLA_PELNY) or (w3 >= KONTROLA_PELNY)
        gruby = (np.isfinite(dx) and dx > 0 and np.isfinite(wys)
                 and wys < SMUKLOSC_DO_WYS and wys / dx < SMUKLOSC_KRZEWU)
        powod = ""
        wyraznie_pusty = (
            o13 is not None and o13.punktow >= PIERSNICA_MIN_PUNKTOW and
            all(not np.isfinite(w) or w < ZLOM_PUSTY for w in (w13, w3))
            and np.isfinite(w13))
        if gruby and wyraznie_pusty:
            ocena = "złom"           # prawdziwy pień, ale złamany
            powod = J.t(f"złamane drzewo: pusty pień {dx * 100:.0f} cm, "
                      f"wysokość tylko {wys:.1f} m",
                      f"broken tree: hollow stem {dx * 100:.0f} cm, "
                      f"height only {wys:.1f} m")
        elif gruby:
            ocena = "krzew"          # za gruby jak na swoją wysokość
            powod = J.t(f"za gruby jak na wysokość: {wys:.1f} m przy "
                      f"{dx * 100:.0f} cm, bez pustego pnia (pniak albo "
                      f"kępa krzewów)",
                      f"too thick for its height: {wys:.1f} m at "
                      f"{dx * 100:.0f} cm, no hollow stem (stump or "
                      f"clump of shrubs)")
        elif not pusty and (not np.isfinite(wys) or wys < niskie):
            ocena = "krzew"
            powod = (J.t(f"punkty w środku przekroju pnia, wysokość "
                       f"{wys:.1f} m", f"points inside the stem "
                       f"cross-section, height {wys:.1f} m")
                     if np.isfinite(wys) else
                     J.t("brak pustego pnia", "no hollow stem"))
        elif pelny:
            ocena = "niepewny"
        else:
            ocena = "ok"
        pewna = bool(o13 is not None and abs(o13.wysokosc_m - 1.3) <= 0.25
                     and o13.punktow >= PIERSNICA_MIN_PUNKTOW
                     and o13.pokrycie_deg >= PIERSNICA_MIN_POKRYCIE
                     and w13 < KONTROLA_PUSTY and ocena != "krzew")
        if ocena == "niepewny":
            powod = J.t("punkty w środku przekroju pnia",
                      "points inside the stem cross-section")
        wyn.append((round(w13, 3) if np.isfinite(w13) else np.nan,
                    round(w3, 3) if np.isfinite(w3) else np.nan,
                    ocena, pewna, powod))
    w = pd.DataFrame(wyn, columns=["wnetrze_13", "wnetrze_3m",
                                   "kontrola_pnia", "srednica_13_pewna",
                                   "kontrola_powod"])
    tab = pd.concat([tab.reset_index(drop=True), w], axis=1)
    n = tab.kontrola_pnia.value_counts()
    print(J.t(f"         kontrola pnia: ok {n.get('ok', 0)}, niepewne "
            f"{n.get('niepewny', 0)}, złomy {n.get('złom', 0)}, krzewy "
            f"(pominiete w wynikach) {n.get('krzew', 0)}",
            f"         stem check: ok {n.get('ok', 0)}, uncertain "
            f"{n.get('niepewny', 0)}, snags {n.get('złom', 0)}, shrubs "
            f"(excluded from results) {n.get('krzew', 0)}"), flush=True)
    if "grupa_gatunkowa" in tab:
        tab.loc[tab.kontrola_pnia == "krzew", "gatunek"] = "nieokreślony"
        tab.loc[tab.kontrola_pnia == "krzew", "grupa_gatunkowa"] = \
            "nieokreślone"
    return tab


def oddziel_podszyt(xyz, h, drzewo, czesc, okregi, do_m, odl_m):
    """Krzaki wokół dołu pnia przypisane w kroku 1 do drzewa: punkty
    gałęzi i ulistnienia niżej niż do_m i dalej od osi pnia niż odl_m
    to podszyt, nie korona drzewa."""
    if not do_m or not len(okregi):
        return czesc
    print(J.t(f"\n[PODSZYT] Oddzielam krzaki przy pniu (poniżej {do_m:g} m, "
            f"dalej niż {odl_m:g} m od pnia)",
            f"\n[UNDERSTORY] Separating shrubs near the stem (below "
            f"{do_m:g} m, farther than {odl_m:g} m from the stem)"),
          flush=True)
    czesc = czesc.copy()
    kand = np.flatnonzero((drzewo > 0) & (h < do_m) &
                          np.isin(czesc, (GALEZ, LISC)))
    if not len(kand):
        return czesc
    # oś pnia: środek najniższego zmierzonego okręgu (albo dorysowanego)
    o = okregi.sort_values("wysokosc_m").groupby("treeID").first()
    sx = pd.Series(o.srodek_x).reindex(drzewo[kand]).to_numpy()
    sy = pd.Series(o.srodek_y).reindex(drzewo[kand]).to_numpy()
    r = pd.Series(o.srednica_m / 2).reindex(drzewo[kand]).fillna(0)\
        .to_numpy()
    d = np.hypot(xyz[kand, 0] - sx, xyz[kand, 1] - sy)
    zle = np.isfinite(d) & (d > odl_m + r)
    czesc[kand[zle]] = PODSZYT
    print(J.t(f"         punktów podszytu: {zle.sum():,}".replace(",", " "),
            f"         understory points: {zle.sum():,}"), flush=True)
    return czesc


def krok6_zapisz(las, xyz, drzewo, czesc, p_pkt, tab, okregi, katalog,
                 nazwa, pole_drzewa):
    print(J.t(f"\n[KROK 6] Zapis do {katalog}",
            f"\n[STEP 6] Saving to {katalog}"))
    katalog.mkdir(parents=True, exist_ok=True)
    naglowek = laspy.LasHeader(point_format=6, version="1.4")
    naglowek.scales = np.array([0.001, 0.001, 0.001])
    naglowek.offsets = np.floor(xyz.min(axis=0))
    for n, typ in (("treeID", np.int32), ("czesc", np.uint8),
                   ("p_drewno", np.float32)):
        naglowek.add_extra_dim(laspy.ExtraBytesParams(name=n, type=typ))
    out = laspy.LasData(naglowek)
    out.x, out.y, out.z = xyz[:, 0], xyz[:, 1], xyz[:, 2]
    out.treeID = drzewo.astype(np.int32)
    out.czesc = czesc
    out.p_drewno = p_pkt
    # klasyfikacja LAS, zeby CloudCompare/QGIS od razu kolorowaly:
    # 0 nic, 1 pien, 2 galezie, 3 ulistnienie, 4 podszyt -> 1, 20, 21, 5, 3
    out.classification = np.choose(czesc, [1, 20, 21, 5, 3]).astype(np.uint8)
    out.write(U.katalog(katalog, U.CHMURY) / f"{nazwa}_czesci.laz")

    # tabela per drzewo
    uz = drzewo > 0
    df = pd.DataFrame({"treeID": drzewo[uz], "c": czesc[uz]})
    udz = (pd.crosstab(df.treeID, df.c, normalize="index") * 100).round(1)
    udz = udz.rename(columns={k: f"proc_{v}" for k, v in NAZWY.items()})
    tab = tab.merge(udz, left_on="treeID", right_index=True, how="left")
    tabele = U.katalog(katalog, U.TABELE)
    tab.to_csv(tabele / f"{nazwa}_czesci_drzewa.csv", index=False)
    okregi.to_csv(tabele / f"{nazwa}_pien_okregi.csv", index=False)
    print(f"         {nazwa}_czesci.laz, {nazwa}_czesci_drzewa.csv, "
          f"{nazwa}_pien_okregi.csv")
    return tab


# ======================================================================
# EKSPORT DO GEOPACKAGE (QGIS)
# ======================================================================
PRZEKROJE = ((1.3, "1_3m"), (3.0, "3m"))
PAS_PUNKTOW = 0.05           # plaster punktów: wysokość ± tyle [m]
MAX_PKT_PRZEKROJU = 1500     # najwięcej punktów jednego drzewa w plastrze
                             # (po przerzedzeniu siatką, zwykle 100-400)


def eksport_gpkg(las, xyz, h, drzewo, czesc, tab, okregi, katalog, nazwa):
    print(J.t("\n[GPKG] Zapis warstw GeoPackage",
            "\n[GPKG] Saving GeoPackage layers"), flush=True)
    srs = G.uklad_skanu(las)
    G.zapisz_srs(U.katalog(katalog, U.TABELE) / f"{nazwa}_uklad.json", srs)
    plik = U.katalog(katalog, U.RAPORT) / f"{nazwa}.gpkg"
    if plik.exists():
        plik.unlink()
    rng = np.random.default_rng(0)
    kolejnosc = np.argsort(drzewo, kind="stable")
    ds = drzewo[kolejnosc]
    tab = tab.reset_index(drop=True)
    zapis = {}

    # drzewa - punkt na pozycji pnia (raport dopisze potem pierśnicę,
    # miąższość i gatunek)
    zapis["drzewa"] = G.zapisz_warstwe(
        plik, "drzewa", "POINT",
        [(x, y) for x, y in zip(tab.pozycja_x, tab.pozycja_y)], tab, srs=srs,
        opis=J.t("drzewa: pozycja pnia i dane z kroku 2",
               "trees: stem position and data from step 2"))

    warstwy = {k: ([], []) for _, k in PRZEKROJE}
    pkt = {k: ([], []) for _, k in PRZEKROJE}
    for t in tab.treeID:
        a, b = np.searchsorted(ds, t), np.searchsorted(ds, t, "right")
        idx = kolejnosc[a:b]
        if not len(idx):
            continue
        o = okregi[okregi.treeID == t].sort_values("wysokosc_m") \
            if len(okregi) else okregi
        r_ = tab.loc[tab.treeID == t].iloc[0]
        for zz, k in PRZEKROJE:
            w = None
            if len(o):
                j = (o.wysokosc_m - zz).abs().idxmin()
                if abs(o.wysokosc_m[j] - zz) <= 0.15 and o.srednica_m[j] > 0:
                    w = o.loc[j]
                    warstwy[k][0].append(G.okrag(w.srodek_x, w.srodek_y,
                                                 w.srednica_m / 2))
                    wn = r_.get("wnetrze_13" if k == "1_3m" else "wnetrze_3m")
                    warstwy[k][1].append({
                        "treeID": t, "wysokosc_m": float(w.wysokosc_m),
                        "srednica_cm": round(float(w.srednica_m) * 100, 1),
                        "pokrycie_deg": w.pokrycie_deg,
                        "punktow": w.punktow, "zrodlo": w.zrodlo,
                        "punkty_w_srodku": wn,
                        "kontrola_pnia": r_.get("kontrola_pnia")})
            m = np.abs(h[idx] - zz) <= PAS_PUNKTOW
            ip = idx[m]
            # przerzedzenie z rozwagą: kora co 1 cm (łuk pnia zostaje),
            # reszta co 4 cm; zamiast tysięcy punktów w jednym miejscu
            nz = np.array([NAZWY[c] for c in czesc[ip]])
            zo = G.przerzedz_plaster(xyz[ip, :2], nz)
            ip, nz = ip[zo], nz[zo]
            if len(ip) > MAX_PKT_PRZEKROJU:
                wyb = np.sort(rng.choice(len(ip), MAX_PKT_PRZEKROJU,
                                         replace=False))
                ip, nz = ip[wyb], nz[wyb]
            at_p = pd.DataFrame({"treeID": t, "czesc": nz})
            if w is not None:          # odległość od okręgu pnia [cm]
                at_p["odl_od_okregu_cm"] = np.round((np.hypot(
                    xyz[ip, 0] - w.srodek_x, xyz[ip, 1] - w.srodek_y)
                    - w.srednica_m / 2) * 100, 1)
            pkt[k][0].append(xyz[ip])
            pkt[k][1].append(at_p)

    for _, k in PRZEKROJE:
        zapis[f"przekroj_{k}"] = G.zapisz_warstwe(
            plik, f"przekroj_{k}", "POLYGON", warstwy[k][0],
            pd.DataFrame(warstwy[k][1]), srs=srs,
            opis=J.t(f"okrąg pnia na {k.replace('_', ',')}",
                   f"stem circle at {k.replace('_', '.')}"))
        xyz_k = np.vstack(pkt[k][0]) if pkt[k][0] else np.zeros((0, 3))
        at_k = pd.concat(pkt[k][1], ignore_index=True) if pkt[k][1] \
            else pd.DataFrame({"treeID": [], "czesc": []})
        zapis[f"punkty_{k}"] = G.zapisz_warstwe(
            plik, f"punkty_{k}", "POINT", xyz_k, at_k, z=True, srs=srs,
            opis=J.t(f"punkty chmury w plastrze {k.replace('_', ',')} "
                   f"±{PAS_PUNKTOW * 100:.0f} cm",
                   f"cloud points in the slice {k.replace('_', '.')} "
                   f"±{PAS_PUNKTOW * 100:.0f} cm"))
    uk = f"EPSG:{srs[0]}" if srs[0] > 0 else J.t("lokalny (skan bez układu)",
                                               "local (scan without CRS)")
    print(f"         {plik.name}: " + ", ".join(
        f"{G.WARSTWY_EN.get(k, k) if J.EN else k} {n}"
        for k, n in zapis.items()) +
          J.t(f"\n         układ współrzędnych: {uk}",
            f"\n         coordinate system: {uk}"), flush=True)


def miarka(ax, x0, y0, dlugosc_cm):
    """Linijka w centymetrach: kreski co 1 cm (albo 5 cm), opis co 10 cm."""
    drobna = 1 if dlugosc_cm <= 30 else 5
    ax.plot([x0, x0 + dlugosc_cm], [y0, y0], color="k", lw=1.6,
            solid_capstyle="butt")
    for c in range(0, int(dlugosc_cm) + 1, drobna):
        dl = 2.2 if c % 10 == 0 else (1.4 if c % 5 == 0 else 0.8)
        ax.plot([x0 + c, x0 + c], [y0, y0 + dl], color="k", lw=0.8)
        if c % 10 == 0:
            ax.text(x0 + c, y0 - 1.2, f"{c}", ha="center", va="top", fontsize=8)
    ax.text(x0 + dlugosc_cm + 1.5, y0, "cm", va="center", fontsize=8)


def podglad(xyz, h, drzewo, czesc, okregi, katalog, nazwa):
    """
    Karta KAZDEGO drzewa, po kolei wedlug numeru:
      lewo, srodek - widok z boku (dwa kierunki), wysokosc nad gruntem w m,
                     odleglosc od osi pnia w m, czerwona linia na 1.3 m
      prawo        - plaster na 1.3 m z gory, w centymetrach, z dopasowanym
                     okregiem pnia i linijka - piersnice da sie odczytac okiem
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Wedge
    tr = J.t                    # t to tu numer drzewa
    from matplotlib.ticker import MultipleLocator

    U.uporzadkuj(katalog)
    kat = U.katalog(katalog, U.OBRAZY)
    for stary in kat.glob("drzewo_*.png"):      # bez obrazkow z poprzednich przebiegow
        stary.unlink()
    kolory = np.array([[.7, .7, .7], [.45, .22, .05], [.85, .55, .2],
                       [.2, .6, .2], [.62, .66, .78]])

    # piersnica z tree_segmenter_tool, jesli jego tabela lezy obok
    dbh_tst = {}
    tab_tst = U.plik(katalog, f"{nazwa}_drzewa.csv")
    grupy, gatunki, kontrola, pewna = {}, {}, {}, {}
    try:
        t_ = pd.read_csv(U.plik(katalog, f"{nazwa}_czesci_drzewa.csv"))
        grupy = dict(zip(t_.treeID, t_.grupa_gatunkowa))
        gatunki = dict(zip(t_.treeID, t_.gatunek)) if "gatunek" in t_ \
            else {}
        kontrola = dict(zip(t_.treeID, t_.kontrola_pnia))
        pewna = dict(zip(t_.treeID, t_.srednica_13_pewna))
    except Exception:                              # noqa: BLE001
        pass
    if tab_tst.exists():
        try:
            t_ = pd.read_csv(tab_tst)
            dbh_tst = dict(zip(t_.id_drzewa, t_.dbh_m))
        except Exception:                          # noqa: BLE001
            pass

    numery = sorted(int(t) for t in np.unique(drzewo) if t > 0)
    cyfry = max(3, len(str(numery[-1]))) if numery else 3
    kolej = np.argsort(drzewo, kind="stable")
    ds = drzewo[kolej]
    rng = np.random.default_rng(0)
    gr_ok = dict(tuple(okregi.groupby("treeID"))) if len(okregi) else {}
    # ścieżka skanera (jeśli jest): z których stron widać było pień
    sc = SC.dla_skanu(katalog, nazwa, xy_skanu=xyz[::997, :2])
    sc_xy = SC.uprosc(sc["xyz"], 0.1)[:, :2] if sc else None

    for nr, t in enumerate(numery, start=1):
        a, b = np.searchsorted(ds, [t, t + 1])
        wsz = kolej[a:b]

        # --- os pnia i piersnica z okregow LidarTreeSegmenter ---
        ok = gr_ok.get(t)
        dbh = None
        dbh_rek = False
        rek = ok[ok.zrodlo == "rekonstrukcja"] if ok is not None else None
        if ok is not None and len(ok) >= 3 and ok.wysokosc_m.min() <= 1.3 <= ok.wysokosc_m.max():
            H = ok.wysokosc_m.to_numpy()
            cx = float(np.interp(1.3, H, ok.srodek_x)); cy = float(np.interp(1.3, H, ok.srodek_y))
            dbh = float(np.interp(1.3, H, ok.srednica_wygladzona_m))
            zm = ok[ok.zrodlo == "pomiar"]
            dbh_rek = len(zm) == 0 or 1.3 < zm.wysokosc_m.min() - P.PIEN_KROK / 2
        else:
            nis = wsz[(h[wsz] > 1.0) & (h[wsz] < 1.6)]
            src = nis if len(nis) else wsz
            cx, cy = np.median(xyz[src, 0]), np.median(xyz[src, 1])

        m = wsz
        if len(m) > 150_000:                    # do rysowania wystarczy probka
            m = rng.choice(m, 150_000, replace=False)
        m = m[np.argsort(czesc[m] == PIEN, kind="stable")]   # pien na wierzchu
        wys = float(np.percentile(h[wsz], 99.9))

        fig = plt.figure(figsize=(15, 8.5))
        gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 1.25], wspace=0.28)
        for k, (i, srodek, opis) in enumerate((
                (0, cx, J.t("wschód – zachód", "east – west")),
                (1, cy, J.t("północ – południe", "north – south")))):
            ax = fig.add_subplot(gs[0, k])
            ax.scatter(xyz[m, i] - srodek, h[m], s=0.3, c=kolory[czesc[m]],
                       linewidths=0, rasterized=True)
            if rek is not None and len(rek):
                # dorysowany (zrekonstruowany) dol pnia - jako walec
                xs = (rek.srodek_x if i == 0 else rek.srodek_y).to_numpy() - srodek
                rr = rek.srednica_wygladzona_m.to_numpy() / 2
                ax.fill_betweenx(rek.wysokosc_m.to_numpy(), xs - rr, xs + rr,
                                 color=DORYSOWANY, alpha=0.35, lw=0)
                ax.plot(xs - rr, rek.wysokosc_m, color=DORYSOWANY, lw=1.2)
                ax.plot(xs + rr, rek.wysokosc_m, color=DORYSOWANY, lw=1.2)
            ax.axhline(1.3, color="#d62728", lw=1, ls="--")
            ax.text(ax.get_xlim()[0], 1.3, J.t(" 1,3 m", " 1.3 m"),
                    color="#d62728",
                    va="bottom", fontsize=8)
            ax.set_aspect("equal")
            ax.set_ylim(min(0, h[m].min()), wys * 1.03 + 0.5)
            ax.yaxis.set_major_locator(MultipleLocator(5))
            ax.yaxis.set_minor_locator(MultipleLocator(1))
            ax.xaxis.set_major_locator(MultipleLocator(2 if wys < 25 else 5))
            ax.xaxis.set_minor_locator(MultipleLocator(1))
            ax.grid(which="major", color="#ccc", lw=0.6)
            ax.grid(which="minor", color="#eee", lw=0.4)
            ax.set_axisbelow(True)
            ax.set_ylabel(J.t("wysokość nad gruntem [m]",
                            "height above ground [m]"))
            ax.set_xlabel(J.t(f"odległość od osi pnia [m]   ({opis})",
                            f"distance from stem axis [m]   ({opis})"))

        # --- plaster 1.3 m z gory, w cm ---
        ax = fig.add_subplot(gs[0, 2])
        pl = wsz[np.abs(h[wsz] - 1.3) <= 0.05]
        dx = (xyz[pl, 0] - cx) * 100; dy = (xyz[pl, 1] - cy) * 100
        R = dbh * 50 if dbh else 15
        zasieg = max(R * 1.7, 20)
        w = (np.abs(dx) < zasieg * 1.2) & (np.abs(dy) < zasieg * 1.2)
        ax.scatter(dx[w], dy[w], s=3, c=kolory[czesc[pl][w]], linewidths=0)
        if dbh:
            ax.add_patch(Circle((0, 0), R, fill=False,
                                color=DORYSOWANY if dbh_rek else "#d62728",
                                lw=1.6, ls="--" if dbh_rek else "-"))
            ax.plot([-R, R], [0, 0], color="#d62728", lw=1, ls=":")
            ax.plot(0, 0, "+", color="#d62728")
        sc_opis = None
        if sc_xy is not None:
            # pierścień wokół pnia: sektory, z których ścieżka skanera była
            # bliżej niż 15 m (stąd skaner mógł widzieć korę)
            dd = sc_xy - (cx, cy)
            od = np.hypot(dd[:, 0], dd[:, 1])
            bl = od <= SC.ZASIEG_WIDOCZNOSCI_M
            kat_s = np.degrees(np.arctan2(dd[bl, 1], dd[bl, 0])) % 360
            szer = 360 / SC.SEKTORY
            widz = np.unique((kat_s // szer).astype(int))
            r_pier = min(R * 1.25 + 2, zasieg * 0.95)
            for k_ in widz:
                ax.add_patch(Wedge((0, 0), r_pier, k_ * szer, (k_ + 1) * szer,
                                   width=max(zasieg * 0.06, 1.5),
                                   color="#7b8aa8", alpha=0.45, lw=0))
            if len(od):
                kn = int(np.argmin(od))
                kier = np.degrees(np.arctan2(dd[kn, 1], dd[kn, 0]))
                ux, uy = np.cos(np.radians(kier)), np.sin(np.radians(kier))
                ax.annotate("", xy=(ux * zasieg * 0.98, uy * zasieg * 0.98),
                            xytext=(ux * (r_pier + 1), uy * (r_pier + 1)),
                            arrowprops=dict(arrowstyle="->", color="#4a5a7a",
                                            lw=1.3))
                sc_opis = tr(f"ścieżka skanera: {od.min():.1f} m od pnia "
                             f"(strzałka), obejście {len(widz) * szer:.0f}°",
                             f"scanner path: {od.min():.1f} m from the stem "
                             f"(arrow), seen from {len(widz) * szer:.0f}°")
        ax.set_aspect("equal")
        ax.set_xlim(-zasieg, zasieg)
        ax.set_ylim(-zasieg * 1.35, zasieg)
        krok = next(k for k in (5, 10, 20, 25, 50, 100) if zasieg / k <= 5)
        ax.xaxis.set_major_locator(MultipleLocator(krok))
        ax.yaxis.set_major_locator(MultipleLocator(krok))
        ax.grid(color="#e4e4e4", lw=0.6); ax.set_axisbelow(True)
        ax.set_xlabel("[cm]"); ax.set_ylabel("[cm]")
        dl = 10 if R * 2 < 25 else (20 if R * 2 < 45 else 50)
        if dl > zasieg * 1.6:
            dl = 10
        miarka(ax, -dl / 2, -zasieg * 1.18, dl)
        opisy = []
        if dbh:
            opisy.append(tr(f"pierśnica {J.NAZWA}: {dbh*100:.1f} cm",
                            f"DBH {J.NAZWA}: {dbh*100:.1f} cm") +
                         (tr("  (DORYSOWANA - pień zasłonięty)",
                             "  (RECONSTRUCTED - stem hidden)") if dbh_rek else
                          "" if pewna.get(t, True) else
                          tr("  (niepewna - mało punktów)",
                             "  (uncertain - few points)")))
        else:
            opisy.append(tr("pierśnicy nie zmierzono (brak pnia na 1,3 m)",
                            "DBH not measured (no stem at 1.3 m)"))
        d2 = dbh_tst.get(t)
        if d2 is not None and d2 == d2:
            opisy.append(tr(f"pierśnica tree_segmenter: {d2*100:.1f} cm",
                            f"DBH tree_segmenter: {d2*100:.1f} cm"))
        if sc_opis:
            opisy.append(sc_opis)
        ax.set_title(tr("plaster na 1,3 m (±5 cm), widok z góry\n",
                        "slice at 1.3 m (±5 cm), top view\n") +
                     "\n".join(opisy), fontsize=10)

        tyt = tr(f"Drzewo {t}   ·   wysokość {wys:.1f} m",
                 f"Tree {t}   ·   height {wys:.1f} m")
        if dbh and d2 is not None and d2 == d2 and \
                abs(dbh - d2) / min(dbh, d2) > 0.3:
            # dwie metody się nie zgadzają - raport wybierze tę, która
            # lepiej pasuje do wysokości drzewa
            tyt += tr(f"   ·   pierśnica {d2*100:.1f} albo {dbh*100:.1f} cm "
                      f"(dwie metody, wybór w raporcie)",
                      f"   ·   DBH {d2*100:.1f} or {dbh*100:.1f} cm "
                      f"(two methods, chosen in the report)")
        elif dbh:
            tyt += tr(f"   ·   pierśnica {dbh*100:.1f} cm",
                      f"   ·   DBH {dbh*100:.1f} cm") + (
                tr(" (szacowana)", " (estimated)") if dbh_rek else "")
        if kontrola.get(t) == "krzew":
            tyt += tr("   ·   PRAWDOPODOBNIE KRZEW (pominięty w wynikach)",
                      "   ·   PROBABLY A SHRUB (excluded from results)")
        elif kontrola.get(t) == "złom":
            tyt += tr("   ·   ZŁOM (złamane drzewo, miąższość ze zmierzonej "
                      "strzały)", "   ·   SNAG (broken tree, volume from the "
                      "measured stem)")
        elif kontrola.get(t) == "niepewny":
            tyt += tr("   ·   niepewny: punkty w środku przekroju",
                      "   ·   uncertain: points inside the cross-section")
        if grupy.get(t, "nieokreślone") != "nieokreślone":
            tyt += tr(f"   ·   {gatunki.get(t, grupy[t])} ({grupy[t]}, "
                      f"wstępnie)", f"   ·   "
                      f"{J.gatunek(gatunki.get(t, grupy[t]))} "
                      f"({J.gatunek(grupy[t])}, preliminary)")
        leg = tr("brąz: pień    pomarańczowy: gałęzie    zielony: ulistnienie    szaroniebieski: podszyt",
                 "brown: stem    orange: branches    green: foliage    "
                 "grey-blue: understory")
        if rek is not None and len(rek):
            leg += tr("    niebieski: dorysowany pień",
                      "    blue: reconstructed stem")
        if sc_xy is not None:
            leg += tr("    szary pierścień: strony widziane ze ścieżki skanera",
                      "    grey ring: sides seen from the scanner path")
        fig.suptitle(tyt + "\n" + leg, fontsize=12)
        fig.savefig(kat / f"drzewo_{t:0{cyfry}d}.png", dpi=100,
                    bbox_inches="tight")
        plt.close(fig)
        print(tr(f"         narysowano {nr} z {len(numery)}",
                 f"         drawn {nr} of {len(numery)}"), flush=True)
    print(tr(f"         podglad: {len(numery)} obrazkow (wszystkie drzewa) "
             f"w {kat}", f"         preview: {len(numery)} images (all "
             f"trees) in {kat}"))


# ======================================================================
def main():
    ap = argparse.ArgumentParser(
        description=J.t("Podzial drzewa na pien, galezie i ulistnienie",
                      "Split trees into stem, branches and foliage"))
    ap.add_argument("plik", type=Path,
                    help=J.t("chmura z numerami drzew (np. *_segmenty.laz)",
                           "point cloud with tree numbers (*_segmenty.laz)"))
    ap.add_argument("--wyniki", type=Path, default=ROOT / "wyniki",
                    help=J.t("folder na wyniki (domyslnie LidarTreeSegmenter\\wyniki)",
                           "results folder (default LidarTreeSegmenter\\wyniki)"))
    ap.add_argument("--bez-obrazkow", action="store_true",
                    help=J.t("nie rysuj obrazkow drzew (szybciej)",
                           "do not draw tree images (faster)"))
    ap.add_argument("--bez-rozdzielania", action="store_true",
                    help=J.t("nie rozdzielaj drzew z dwoma pniami",
                             "do not split trees with two stems"))
    ap.add_argument("--prog", type=float, default=None,
                    help=J.t(f"prog p_drewno (domyslnie {P.PROG_DREWNA})",
                           f"p_wood threshold (default {P.PROG_DREWNA})"))
    a = ap.parse_args()
    if not a.plik.is_file():
        sys.exit(J.t(f"BLAD: nie ma takiego pliku: {a.plik}",
                   f"ERROR: no such file: {a.plik}"))
    if a.prog is not None:
        P.PROG_DREWNA = a.prog

    t0 = time.time()
    las, xyz, drzewo, h, pole = krok1_wczytaj(a.plik)
    teren = None
    if any(p in {d.name for d in las.point_format.dimensions}
           for p in POLA_WYSOKOSCI):
        try:                          # model terenu z wysokości nad gruntem
            teren = DTM.z_chmury(xyz, h)
        except Exception as e:                     # noqa: BLE001
            print(J.t(f"         UWAGA: model terenu się nie udał ({e})",
                      f"         WARNING: terrain model failed ({e})"),
                  flush=True)
    Z.pokaz(J.t("Drzewa z etapu 1 (kolor = drzewo)",
              "Trees from stage 1 (colour = tree)"), xyz, drzewo, "drzewa")
    rozdz = None
    if not a.bez_rozdzielania:
        poz = {}
        n_ = a.plik.stem.replace("_segmenty", "")
        p_d = U.plik(a.wyniki / n_, f"{n_}_drzewa.csv")
        if p_d.exists():
            d1 = pd.read_csv(p_d)
            if {"id_drzewa", "pozycja_x", "pozycja_y"} <= set(d1):
                poz = {int(r.id_drzewa): (float(r.pozycja_x),
                                          float(r.pozycja_y))
                       for r in d1.itertuples()}
        drzewo, rozdz = rozdziel_zrosniete(xyz, h, drzewo, poz)
    jest_pniem, tab, okregi = krok2_pnie(xyz, drzewo, h)
    if Z.wlaczony() and len(okregi):
        o13 = okregi.loc[(okregi.wysokosc_m - 1.3).abs() < 0.11]
        Z.pokaz(J.t("Pnie prześledzone do korony (brąz = pień, okręgi na "
                  "1,3 m)", "Stems traced up to the crown (brown = stem, "
                  "circles at 1.3 m)"),
                xyz, np.where(jest_pniem, 1, 3 * (drzewo > 0)), "czesci",
                np.column_stack([o13.srodek_x, o13.srodek_y,
                                 o13.srednica_m / 2]))
    V = krok3_cechy(xyz, drzewo, h, jest_pniem, tab)
    p_vox = krok4_drewno_lisc(V)
    klasa_vox = krok5_sprzatanie(V, p_vox)

    czesc = np.zeros(len(xyz), np.uint8)
    p_pkt = np.zeros(len(xyz), np.float32)
    czesc[V["idx_uz"]] = klasa_vox[V["odwr"]]
    p_pkt[V["idx_uz"]] = p_vox[V["odwr"]]
    # punkt pnia zawsze pniem, nawet gdy jego voxel przewazyl inaczej
    czesc[jest_pniem & (czesc > 0)] = PIEN
    Z.pokaz(J.t("Pień, gałęzie i ulistnienie", "Stem, branches and foliage"),
            xyz, czesc, "czesci")

    nazwa = a.plik.stem.replace("_segmenty", "")
    katalog = a.wyniki / nazwa
    klasa, par, auto = UST.klasa_skanu(katalog, nazwa,
                                       tab.get("srednica_13_m"))
    print(J.t(f"\n  Klasa drzewostanu: {klasa}"
            f"{' (dobrana z pierśnic)' if auto else ''}",
            f"\n  Stand class: {J.klasa(klasa)}"
            f"{' (chosen from DBH)' if auto else ''}"), flush=True)
    UST.zapisz(katalog, nazwa, klasa_uzyta=klasa)
    tab = rozpoznaj_grupe(xyz, h, drzewo, tab, okregi)
    gat = UST.gatunek_skanu(katalog, nazwa)
    if gat:
        tab["gatunek"] = gat
        print(J.t(f"  Gatunek na całej powierzchni: {gat}",
                f"  Species for the whole plot: {J.gatunek(gat)}"),
              flush=True)
    tab = kontrola_pnia(xyz, h, drzewo, tab, okregi,
                        par.get("wysokosc_krzewu_m"))
    czesc = oddziel_podszyt(xyz, h, drzewo, czesc, okregi,
                            par.get("podszyt_do_m", 0),
                            par.get("podszyt_odleglosc_m", 1.0))
    tab = krok6_zapisz(las, xyz, drzewo, czesc, p_pkt, tab, okregi, katalog,
                       nazwa, pole)
    if rozdz is not None:
        rozdz.to_csv(U.katalog(katalog, U.TABELE) / f"{nazwa}_rozdzielone.csv",
                     index=False)
    try:
        eksport_gpkg(las, xyz, h, drzewo, czesc, tab, okregi, katalog, nazwa)
    except Exception as e:                         # noqa: BLE001
        print(J.t(f"         UWAGA: GeoPackage się nie zapisał ({e}) - reszta "
                f"wyników jest w porządku",
                f"         WARNING: the GeoPackage was not saved ({e}) - "
                f"the other results are fine"), flush=True)
    if teren is not None:
        try:
            DTM.zapisz(U.katalog(katalog, U.TABELE) / f"{nazwa}_teren.npz",
                       teren)
            st = DTM.statystyki(teren)
            n_w = DTM.do_gpkg(U.katalog(katalog, U.RAPORT) / f"{nazwa}.gpkg",
                              teren, G.uklad_skanu(las))
            print(J.t(f"         teren: deniwelacja {st['deniwelacja']:.1f} m,"
                      f" średni spadek {st['spadek_sr']:.0f}°, ekspozycja "
                      f"{st['ekspozycja']}, warstwic {n_w}",
                      f"         terrain: relief {st['deniwelacja']:.1f} m, "
                      f"mean slope {st['spadek_sr']:.0f}°, aspect "
                      f"{st['ekspozycja']}, contours {n_w}"), flush=True)
        except Exception as e:                     # noqa: BLE001
            print(J.t(f"         UWAGA: warstwy terenu się nie zapisały ({e})",
                      f"         WARNING: terrain layers were not saved "
                      f"({e})"), flush=True)
    if not a.bez_obrazkow:
        podglad(xyz, h, drzewo, czesc, okregi, katalog, nazwa)

    uz = czesc > 0
    print("\n" + "=" * 66)
    print(J.t(f"  GOTOWE w {(time.time()-t0)/60:.1f} min",
            f"  DONE in {(time.time()-t0)/60:.1f} min"))
    for k in (PIEN, GALEZ, LISC):
        print(J.t(f"    {NAZWY[k]:<12} {(czesc[uz] == k).mean()*100:5.1f}% "
                f"punktow", f"    {J.WARTOSCI_EN[NAZWY[k]]:<12} "
                f"{(czesc[uz] == k).mean()*100:5.1f}% of points"))
    print("=" * 66)
    print(J.t(f"\n  Otworz {nazwa}_czesci.laz w CloudCompare i pokoloruj po "
            f"polu 'czesc'\n  (albo po klasyfikacji). Obrazki: "
            f"{katalog / U.OBRAZY}", f"\n  Open {nazwa}_czesci.laz in "
            f"CloudCompare and colour by the field 'czesc'\n  (1 stem, "
            f"2 branches, 3 foliage, 4 understory; or by classification). "
            f"Images: {katalog / U.OBRAZY}"))
    U.uporzadkuj(katalog)


if __name__ == "__main__":
    main()
