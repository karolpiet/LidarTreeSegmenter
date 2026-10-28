"""
WYCINANIE MAŁEGO KAWAŁKA CHMURY (do ćwiczeń)
============================================

Duży skan ma 15 milionów punktów i więcej. Na takim pliku każde ćwiczenie
liczy się długo. Ten program wycina mały kwadrat (domyślnie 6 × 6 m)
i zapisuje go jako osobny, mały plik .laz. Wszystkie pola zostają
(treeID, czesc, wys_nad_grunt itd.), więc ćwiczenia działają tak samo.

Program czyta duży plik KAWAŁKAMI (po milion punktów), więc nie zajmuje
dużo pamięci, nawet przy bardzo dużych skanach.

UŻYCIE (w konsoli, w folderze dane_testowe):

    python make_maly_las.py <duzy.laz>
        -> kwadrat 6 × 6 m ze środka skanu

    python make_maly_las.py <duzy.laz> <X> <Y>
        -> kwadrat 6 × 6 m wokół punktu X, Y (np. wokół wybranego drzewa)

    python make_maly_las.py <duzy.laz> <X> <Y> <bok_m>
        -> kwadrat o podanym boku (np. 10)

    python make_maly_las.py <duzy.laz> <X> <Y> <bok_m> <wynik.laz>
        -> jak wyżej, ale z własną nazwą pliku wynikowego

SKĄD WZIĄĆ X i Y DRZEWA:
    wyniki\\<skan>\\03_TABELE\\<skan>_czesci_drzewa.csv
    kolumny pozycja_x i pozycja_y (otwórz w Excelu).
"""

import sys
from pathlib import Path

import numpy as np

try:
    import laspy
except ImportError:
    sys.exit("BŁĄD: brak biblioteki laspy. Zainstaluj ją poleceniem:\n"
             "      python -m pip install laspy lazrs")


def main():
    # ---- 1. argumenty z konsoli -------------------------------------
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit("BŁĄD: podaj plik .las albo .laz, np.\n"
                 "      python make_maly_las.py ..\\..\\..\\wyniki\\SKAN\\"
                 "02_CHMURY\\SKAN_czesci.laz")

    wejscie = Path(sys.argv[1])
    if not wejscie.exists():
        sys.exit(f"BŁĄD: nie ma pliku {wejscie}")

    with laspy.open(str(wejscie)) as czytnik:
        naglowek = czytnik.header
        mins, maxs = naglowek.mins, naglowek.maxs

        if len(sys.argv) >= 4:
            x0, y0 = float(sys.argv[2]), float(sys.argv[3])
        else:
            # środek skanu (z nagłówka - nie trzeba czytać punktów)
            x0 = (mins[0] + maxs[0]) / 2
            y0 = (mins[1] + maxs[1]) / 2
        bok = float(sys.argv[4]) if len(sys.argv) >= 5 else 6.0
        if len(sys.argv) >= 6:
            wynik = Path(sys.argv[5])
        else:
            # domyślnie obok tego programu, w folderze dane_testowe
            wynik = (Path(__file__).resolve().parent /
                     f"{wejscie.stem}_maly_{x0:.0f}_{y0:.0f}.laz")

        pol = bok / 2
        print(f"Plik:      {wejscie.name}")
        print(f"Punktów:   {naglowek.point_count:,}".replace(",", " "))
        print(f"Wycinam:   kwadrat {bok:g} × {bok:g} m wokół "
              f"X = {x0:.2f}, Y = {y0:.2f}")

        # ---- 2. czytanie kawałkami i zapis tylko punktów w kwadracie --
        zapisane = 0
        with laspy.open(str(wynik), mode="w", header=naglowek) as pisarz:
            for kawalek in czytnik.chunk_iterator(1_000_000):
                x = np.asarray(kawalek.x)
                y = np.asarray(kawalek.y)
                w_kwadracie = (np.abs(x - x0) <= pol) & (np.abs(y - y0) <= pol)
                if w_kwadracie.any():
                    pisarz.write_points(kawalek[w_kwadracie])
                    zapisane += int(w_kwadracie.sum())
                print(".", end="", flush=True)
        print()

    if zapisane == 0:
        wynik.unlink(missing_ok=True)
        sys.exit("BŁĄD: w tym kwadracie nie ma żadnego punktu. Sprawdź X i Y.\n"
                 f"      Zasięg skanu: X {mins[0]:.1f} .. {maxs[0]:.1f}, "
                 f"Y {mins[1]:.1f} .. {maxs[1]:.1f}")
    print(f"Zapisano:  {zapisane:,} punktów".replace(",", " "))
    print(f"Plik:      {wynik}")


if __name__ == "__main__":
    main()
