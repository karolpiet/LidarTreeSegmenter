"""
GENERATOR SZTUCZNEJ CHMURY TESTOWEJ (udaje skan TLS lasu)
=========================================================

Do czego to jest:
    Zanim puścisz pipeline na prawdziwe dane, musisz wiedzieć, czy on dobrze liczy.
    Na prawdziwym skanie nie wiesz, ile naprawdę ma pierśnicy to drzewo w kącie
    poletka - wiec nie wiesz, czy wynik 0.34 m to prawda, czy blad.

    Tutaj SAM USTAWIAM piersnice i wysokosci drzew, a potem sprawdzam, czy pipeline
    je odtworzy. To sie nazywa "ground truth" - prawda odniesienia.

Co generuje:
    - poletko 30 x 30 m
    - grunt z lekkim nachyleniem (bo w lesie nigdy nie jest plasko)
    - 18 drzew: pien (zwezajacy sie ku gorze) + korona
    - szum: pojedyncze punkty wiszace w powietrzu (tak wyglada szum w TLS:
      owady, mgla, odbicia od krawedzi, "ghost points")
    - czesciowe zaslonienia pni (TLS nie widzi pnia z kazdej strony)

Wynik: dwa pliki w podkatalogu dane/
    las_testowy.laz        <- chmura punktow
    las_testowy_prawda.csv <- prawdziwe DBH i wysokosci, do porownania
"""

import numpy as np
import pandas as pd
import argparse
import laspy
from pathlib import Path

# ======================================================================
# USTAWIENIA
# ======================================================================
ZIARNO = 42                 # zeby za kazdym uruchomieniem wyszlo to samo
ROZMIAR_POLETKA = 30.0      # metry (kwadrat 30 x 30)
LICZBA_DRZEW = 18
NACHYLENIE_GRUNTU = 0.06    # 6% spadku - realistyczne dla lasu na zboczu
KATALOG_WYJSCIOWY = Path(__file__).parent / "data"

# Zakres piersnic i wzor na wysokosc. DOMYSLNE WARTOSCI = drzewostan dojrzaly
# (grube drzewa), czyli dokladnie to, co bylo tu od zawsze - nie zmieniaj ich,
# bo na tym opiera sie staly test sprawdzajacy, czy pipeline dziala.
#
# Zeby zrobic drzewostan CIENKI (mlodnik, drzewa od 7 cm), podaj z linii
# polecen wlasne wartosci - patrz --pomoc na koncu pliku.
DBH_MIN = 0.14
DBH_MAX = 0.52
WYS_A = 8.0                 # wysokosc = WYS_A + WYS_B * dbh  (+ szum)
WYS_B = 34.0
WYS_CLIP = (9.0, 30.0)      # w jakich granicach trzymac wysokosc [m]
ODSTEP_DRZEW = 2.0          # minimalna odleglosc miedzy pniami [m]
NAZWA_WYJSCIA = "las_testowy"

rng = np.random.default_rng(ZIARNO)


# ======================================================================
# GRUNT
# ======================================================================
def wysokosc_gruntu(x, y):
    """
    Zwraca wysokosc terenu (Z) w punkcie (x, y).

    Terenu nie robie plaskiego, bo wtedy pipeline przeszedlby test, a na
    prawdziwym zboczu by sie wywalil. Dodaje:
      - stale nachylenie w kierunku X
      - delikatna fale (nierownosci, kopczyki, korzenie)
    """
    return (NACHYLENIE_GRUNTU * np.asarray(x)
            + 0.3 * np.sin(np.asarray(x) / 7.0)
            + 0.25 * np.cos(np.asarray(y) / 5.0))


def generuj_grunt(liczba_punktow=150_000):
    x = rng.uniform(0, ROZMIAR_POLETKA, liczba_punktow)
    y = rng.uniform(0, ROZMIAR_POLETKA, liczba_punktow)
    z = wysokosc_gruntu(x, y)
    z += rng.normal(0, 0.02, liczba_punktow)   # szorstkosc: sciolka, igliwie
    return np.column_stack([x, y, z])


# ======================================================================
# JEDNO DRZEWO
# ======================================================================
def generuj_drzewo(x0, y0, dbh, wysokosc):
    """
    Buduje jedno drzewo stojace w punkcie (x0, y0).

    dbh      - piersnica w metrach (srednica pnia na 1.3 m nad gruntem)
    wysokosc - wysokosc drzewa w metrach (od gruntu do czubka)

    Zwraca (punkty Nx3, klasy N) gdzie klasa: 1 = pien, 2 = korona
    """
    z_gruntu = float(wysokosc_gruntu(x0, y0))
    punkty, klasy = [], []

    # ---------------------------------------------------------------
    # PIEN
    # ---------------------------------------------------------------
    # Pien to nie rura o stalej grubosci - zweza sie ku gorze. To sie nazywa
    # zbiezystosc (ang. taper). Na dole jest szerszy (nabiegi korzeniowe),
    # na 1.3 m ma dokladnie dbh, wyzej coraz cienszy.
    wysokosc_pnia = wysokosc * 0.60          # wyzej zaczyna sie korona
    z_warstwy = np.linspace(0.02, wysokosc_pnia, 500)

    for z_rel in z_warstwy:
        if z_rel < 0.30:
            # NABIEGI KORZENIOWE - pogrubienie przy ziemi.
            # To wlasnie dlatego piersnice mierzy sie na 1.3 m, a nie u podstawy!
            promien = (dbh / 2) * (1.0 + 0.45 * (0.30 - z_rel) / 0.30)
        else:
            zbiezystosc = 0.008   # ubytek promienia na metr wysokosci
            promien = (dbh / 2) - zbiezystosc * (z_rel - 1.3)
            promien = max(promien, 0.02)

        # Ile punktow na tej warstwie - gestosc spada z wysokoscia, bo skaner
        # naziemny widzi gore drzewa pod ostrym katem i przez galezie.
        n = max(5, int(30 * np.exp(-z_rel / 14.0)))
        kat = rng.uniform(0, 2 * np.pi, n)

        # ZASLONIECIE (occlusion): TLS nie widzi pnia z kazdej strony.
        # W 35% warstw wycinam wycinek katowy.
        if rng.random() < 0.35:
            kat_start = rng.uniform(0, 2 * np.pi)
            roznica = np.angle(np.exp(1j * (kat - kat_start)))
            kat = kat[np.abs(roznica) > 0.7]
        if len(kat) == 0:
            continue

        szum = rng.normal(0, 0.006, len(kat))   # dokladnosc skanera ~6 mm
        x = x0 + (promien + szum) * np.cos(kat)
        y = y0 + (promien + szum) * np.sin(kat)
        z = np.full(len(kat), z_gruntu + z_rel) + rng.normal(0, 0.004, len(kat))

        punkty.append(np.column_stack([x, y, z]))
        klasy.append(np.full(len(kat), 1))

    # ---------------------------------------------------------------
    # KORONA - z PRAWDZIWYMI GALEZIAMI
    # ---------------------------------------------------------------
    # WAZNE, dlaczego nie robie korony jako jednolitej kuli punktow:
    #
    #   Gdyby korona byla pelna kula, to korony dwoch sasiadujacych drzew
    #   zlalyby sie w jedna lita bryle bez zadnych przerw. Wtedy ZADNA metoda
    #   segmentacji nie mialaby szansy ich rozdzielic - i test bylby bezsensowny,
    #   bo mierzylby nie jakosc algorytmu, a wade danych.
    #
    #   Prawdziwa korona to galezie: cienkie linie wychodzace z pnia, z liscmi
    #   skupionymi wokol nich, i DUZO PUSTEJ PRZESTRZENI miedzy nimi. Wlasnie
    #   te puste przestrzenie pozwalaja algorytmom rozdzielic drzewa.
    #
    # Dlatego buduje galezie jedna po drugiej.

    promien_korony = max(1.0, dbh * 9.0)
    z_dol = z_gruntu + wysokosc_pnia * 0.70
    z_gora = z_gruntu + wysokosc
    wysokosc_korony = z_gora - z_dol

    n_galezi = int(rng.integers(22, 40))
    xk, yk, zk = [], [], []

    for _ in range(n_galezi):
        # Na jakiej wysokosci galaz wychodzi z pnia (0 = dol korony, 1 = czubek)
        udzial = rng.random() ** 0.8
        z_start = z_dol + udzial * wysokosc_korony

        # KSZTALT KORONY: galezie u dolu sa dlugie, u gory krotkie -
        # stad stozkowy zarys drzewa iglastego.
        dlugosc = promien_korony * (1.0 - 0.75 * udzial) * rng.uniform(0.6, 1.1)
        dlugosc = max(dlugosc, 0.3)

        azymut = rng.uniform(0, 2 * np.pi)
        # Galezie u dolu zwisaja (kat ujemny), u gory ida w gore.
        nachylenie = np.radians(rng.uniform(-18, 12) + 30 * udzial)

        # Punkty wzdluz galezi. Galaz lekko sie wygina - dlatego podnosze
        # koncowke proporcjonalnie do kwadratu odleglosci.
        n_na_galezi = max(12, int(dlugosc * 55))
        t = rng.random(n_na_galezi) ** 0.7        # gesciej przy pniu
        r = t * dlugosc

        gx = x0 + r * np.cos(azymut)
        gy = y0 + r * np.sin(azymut)
        gz = z_start + r * np.tan(nachylenie) + 0.08 * r ** 2

        # grubosc galezi: bliżej pnia grubsza, na koncu cienka
        rozrzut = 0.02 + 0.05 * (1 - t)
        gx += rng.normal(0, rozrzut)
        gy += rng.normal(0, rozrzut)
        gz += rng.normal(0, rozrzut)

        xk.append(gx); yk.append(gy); zk.append(gz)

        # LISCIE / IGLY: skupiska wokol zewnetrznej czesci galezi.
        n_skupisk = int(rng.integers(2, 6))
        for _ in range(n_skupisk):
            t_s = rng.uniform(0.35, 1.0)
            r_s = t_s * dlugosc
            cx_s = x0 + r_s * np.cos(azymut)
            cy_s = y0 + r_s * np.sin(azymut)
            cz_s = z_start + r_s * np.tan(nachylenie) + 0.08 * r_s ** 2

            n_l = int(rng.integers(40, 110))
            promien_skupiska = rng.uniform(0.18, 0.40)
            xk.append(cx_s + rng.normal(0, promien_skupiska, n_l))
            yk.append(cy_s + rng.normal(0, promien_skupiska, n_l))
            zk.append(cz_s + rng.normal(0, promien_skupiska * 0.8, n_l))

    # CZUBEK: przedluzenie pnia ponad ostatnie galezie, zakonczone dokladnie
    # na zadanej wysokosci. Dzieki temu "prawdziwa wysokosc" jest jednoznaczna.
    n_czubek = 90
    t_cz = rng.random(n_czubek)
    z_czubka_dol = z_dol + 0.80 * wysokosc_korony
    xk.append(x0 + rng.normal(0, 0.035, n_czubek))
    yk.append(y0 + rng.normal(0, 0.035, n_czubek))
    zk.append(z_czubka_dol + t_cz * (z_gora - z_czubka_dol))
    # kilka punktow dokladnie na szczycie
    xk.append(x0 + rng.normal(0, 0.02, 5))
    yk.append(y0 + rng.normal(0, 0.02, 5))
    zk.append(z_gora - rng.random(5) * 0.02)

    xk = np.concatenate(xk); yk = np.concatenate(yk); zk = np.concatenate(zk)

    # ZASLONIECIE: skaner naziemny widzi gorne czesci korony slabiej, bo
    # patrzy przez wlasne galezie drzewa. Im wyzej, tym mniej punktow.
    waga = np.exp(-(zk - z_dol) / (0.85 * wysokosc_korony + 1e-9))
    waga = np.clip(waga, 0.10, 1.0)
    # czubek zawsze zostawiam, zeby prawda odniesienia miala sens
    jest_czubkiem = zk > z_gora - 0.05
    zostaw = (rng.random(len(zk)) < waga) | jest_czubkiem

    punkty.append(np.column_stack([xk[zostaw], yk[zostaw], zk[zostaw]]))
    klasy.append(np.full(int(zostaw.sum()), 2))

    return np.vstack(punkty), np.concatenate(klasy)


# ======================================================================
# SZUM
# ======================================================================
def generuj_szum(liczba_punktow=4000):
    """
    Pojedyncze punkty wiszace w powietrzu i pod gruntem.

    Tak wyglada szum w TLS:
      - "ghost points" / mixed pixels: wiazka trafia w krawedz galezi i wraca
        jako punkt w pol drogi miedzy dwoma obiektami
      - owady, kurz, mgla, kropelki deszczu
      - odbicia wielokrotne -> punkty POD gruntem

    Cecha wspolna: te punkty sa SAMOTNE. Nie maja sasiadow. Na tym opiera sie
    filtr SOR w kroku 1 pipeline'u.
    """
    x = rng.uniform(0, ROZMIAR_POLETKA, liczba_punktow)
    y = rng.uniform(0, ROZMIAR_POLETKA, liczba_punktow)
    z_bazowe = wysokosc_gruntu(x, y)
    # wiekszosc nad gruntem, czesc pod (odbicia wielokrotne)
    offset = np.where(rng.random(liczba_punktow) < 0.85,
                      rng.uniform(0.5, 28.0, liczba_punktow),
                      rng.uniform(-2.5, -0.3, liczba_punktow))
    return np.column_stack([x, y, z_bazowe + offset])


# ======================================================================
# SKLEJANIE CALOSCI
# ======================================================================
def main():
    KATALOG_WYJSCIOWY.mkdir(parents=True, exist_ok=True)

    # --- rozmieszczenie drzew ---
    # Nie losuje calkiem przypadkowo, bo drzewa by na siebie nachodzily.
    # Uzywam prostego odrzucania: nowe drzewo musi byc >2.0 m od poprzednich.
    pozycje = []
    prob = 0
    while len(pozycje) < LICZBA_DRZEW and prob < 100000:
        prob += 1
        kandydat = rng.uniform(2.0, ROZMIAR_POLETKA - 2.0, 2)
        if all(np.linalg.norm(kandydat - np.array(p)) > ODSTEP_DRZEW
               for p in pozycje):
            pozycje.append(tuple(kandydat))
    if len(pozycje) < LICZBA_DRZEW:
        print(f"  UWAGA: zmiescilo sie tylko {len(pozycje)} z {LICZBA_DRZEW} "
              f"drzew przy odstepie {ODSTEP_DRZEW} m.")

    wszystkie_punkty = []
    wszystkie_klasy = []
    wszystkie_id = []
    prawda = []

    # --- grunt (klasa 0, id drzewa = 0 czyli "nie drzewo") ---
    g = generuj_grunt()
    wszystkie_punkty.append(g)
    wszystkie_klasy.append(np.zeros(len(g), dtype=np.uint8))
    wszystkie_id.append(np.zeros(len(g), dtype=np.int32))

    # --- drzewa ---
    for i, (x0, y0) in enumerate(pozycje, start=1):
        # Losuje piersnice i wysokosc w realistycznym zakresie dla drzewostanu
        # dojrzalego. Wysokosc skorelowana z piersnica (grubsze = wyzsze),
        # bo tak jest w przyrodzie.
        dbh = rng.uniform(DBH_MIN, DBH_MAX)
        wysokosc = WYS_A + WYS_B * dbh + rng.normal(0, 1.2)
        wysokosc = float(np.clip(wysokosc, *WYS_CLIP))

        p, k = generuj_drzewo(x0, y0, dbh, wysokosc)
        wszystkie_punkty.append(p)
        wszystkie_klasy.append(k.astype(np.uint8))
        wszystkie_id.append(np.full(len(p), i, dtype=np.int32))

        prawda.append({
            "id_drzewa": i,
            "x": round(x0, 3),
            "y": round(y0, 3),
            "dbh_prawdziwy_m": round(dbh, 4),
            "wysokosc_prawdziwa_m": round(wysokosc, 3),
        })

    # --- szum (klasa 7 = "low point/noise", standard LAS) ---
    s = generuj_szum()
    wszystkie_punkty.append(s)
    wszystkie_klasy.append(np.full(len(s), 7, dtype=np.uint8))
    wszystkie_id.append(np.zeros(len(s), dtype=np.int32))

    punkty = np.vstack(wszystkie_punkty)
    klasy = np.concatenate(wszystkie_klasy)
    id_drzew = np.concatenate(wszystkie_id)

    # przetasowanie - w prawdziwym pliku punkty nie sa poukladane po drzewach
    kolejnosc = rng.permutation(len(punkty))
    punkty, klasy, id_drzew = punkty[kolejnosc], klasy[kolejnosc], id_drzew[kolejnosc]

    # ==================================================================
    # ZAPIS DO .laz
    # ==================================================================
    # LAS przechowuje wspolrzedne jako LICZBY CALKOWITE + skala i offset.
    # scales = 0.001 oznacza dokladnosc zapisu 1 mm - w zupelnosci wystarczy.
    naglowek = laspy.LasHeader(point_format=6, version="1.4")
    naglowek.scales = np.array([0.001, 0.001, 0.001])
    naglowek.offsets = np.floor(punkty.min(axis=0))

    # Dodaje wlasne pole "treeID" - tak samo jak w notebooku, ktory przyslales.
    # Dzieki temu w CloudCompare mozna pokolorowac chmure po drzewach.
    naglowek.add_extra_dim(laspy.ExtraBytesParams(name="treeID", type=np.int32))

    las = laspy.LasData(naglowek)
    las.x, las.y, las.z = punkty[:, 0], punkty[:, 1], punkty[:, 2]
    las.classification = klasy
    las.treeID = id_drzew

    sciezka_laz = KATALOG_WYJSCIOWY / f"{NAZWA_WYJSCIA}.laz"
    las.write(sciezka_laz)

    df = pd.DataFrame(prawda)
    sciezka_csv = KATALOG_WYJSCIOWY / f"{NAZWA_WYJSCIA}_prawda.csv"
    df.to_csv(sciezka_csv, index=False)

    # ==================================================================
    # PODSUMOWANIE
    # ==================================================================
    print("=" * 62)
    print("WYGENEROWANO SZTUCZNY SKAN TESTOWY")
    print("=" * 62)
    print(f"  plik chmury : {sciezka_laz}")
    print(f"  prawda      : {sciezka_csv}")
    print(f"  punktow     : {len(punkty):,}")
    print(f"    grunt     : {(klasy == 0).sum():,}")
    print(f"    pnie      : {(klasy == 1).sum():,}")
    print(f"    korony    : {(klasy == 2).sum():,}")
    print(f"    szum      : {(klasy == 7).sum():,}")
    print(f"  drzew       : {len(prawda)}")
    print(f"  DBH         : {df.dbh_prawdziwy_m.min():.3f} - "
          f"{df.dbh_prawdziwy_m.max():.3f} m")
    print(f"  wysokosci   : {df.wysokosc_prawdziwa_m.min():.1f} - "
          f"{df.wysokosc_prawdziwa_m.max():.1f} m")
    print("=" * 62)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description="Generuje sztuczny skan testowy lasu.",
        epilog="Przyklad - drzewostan CIENKI (mlodnik, piersnice od 7 cm):\n"
               "  python 00_generuj_testowy_las.py --dbh 0.07 0.20 "
               "--drzew 30 --odstep 1.2 --wys 3 40 --wys-granice 4 16 "
               "--nazwa las_cienki",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dbh", type=float, nargs=2, metavar=("MIN", "MAX"),
                    default=[DBH_MIN, DBH_MAX],
                    help=f"zakres piersnic w metrach "
                         f"(domyslnie {DBH_MIN} {DBH_MAX})")
    ap.add_argument("--drzew", type=int, default=LICZBA_DRZEW,
                    help=f"ile drzew (domyslnie {LICZBA_DRZEW})")
    ap.add_argument("--odstep", type=float, default=ODSTEP_DRZEW,
                    help=f"minimalna odleglosc miedzy pniami w metrach "
                         f"(domyslnie {ODSTEP_DRZEW})")
    ap.add_argument("--wys", type=float, nargs=2, metavar=("A", "B"),
                    default=[WYS_A, WYS_B],
                    help=f"wysokosc = A + B * dbh (domyslnie {WYS_A} {WYS_B})")
    ap.add_argument("--wys-granice", type=float, nargs=2,
                    metavar=("MIN", "MAX"), default=list(WYS_CLIP),
                    help=f"w jakich granicach trzymac wysokosc "
                         f"(domyslnie {WYS_CLIP[0]} {WYS_CLIP[1]})")
    ap.add_argument("--nazwa", default=NAZWA_WYJSCIA,
                    help=f"nazwa plikow wyjsciowych bez rozszerzenia "
                         f"(domyslnie {NAZWA_WYJSCIA})")
    ap.add_argument("--ziarno", type=int, default=ZIARNO,
                    help=f"ziarno losowosci (domyslnie {ZIARNO})")
    a = ap.parse_args()

    DBH_MIN, DBH_MAX = a.dbh
    LICZBA_DRZEW = a.drzew
    ODSTEP_DRZEW = a.odstep
    WYS_A, WYS_B = a.wys
    WYS_CLIP = tuple(a.wys_granice)
    NAZWA_WYJSCIA = a.nazwa
    rng = np.random.default_rng(a.ziarno)

    main()
