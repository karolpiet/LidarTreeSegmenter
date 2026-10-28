"""
LEKCJA 1 - ROZWIĄZANIE: podstawy Pythona na przykładzie powierzchni próbnej
==========================================================================

Uruchomienie (w konsoli, w folderze KURS_PYTHONA):

    python rozwiazanie_01_podstawy.py
    python rozwiazanie_01_podstawy.py <dowolny_plik.laz>   (opcjonalnie)
"""

import math          # moduł z funkcjami matematycznymi (pi, sqrt ...)
import sys           # moduł "system" - stąd bierzemy argumenty z konsoli
from pathlib import Path


# ---- FUNKCJE -------------------------------------------------------------
def pole_przekroju(d_cm):
    """Pierśnicowe pole przekroju g [m²] z pierśnicy d [cm]."""
    d_m = d_cm / 100                 # centymetry -> metry
    return math.pi / 4 * d_m ** 2    # g = π/4 · d²


def klasa_grubosci(d_cm):
    """Prosty podział na klasy grubości (jak w taksacji)."""
    if d_cm < 7:
        return "nalot / podrost"
    elif d_cm < 20:
        return "drągowina"
    elif d_cm < 35:
        return "drzewostan średni"
    else:
        return "drzewostan dojrzały"


# ---- ZMIENNE I LISTY -----------------------------------------------------
nazwa_powierzchni = "Powierzchnia próbna nr 7"   # tekst (str)
promien_powierzchni = 12.62                      # liczba z przecinkiem (float)
liczba_drzew = 6                                 # liczba całkowita (int)

# lista pierśnic [cm] z "klupowania"
piersnice = [32.5, 41.0, 18.2, 55.4, 6.3, 27.9]
gatunki = ["świerk", "buk", "świerk", "buk", "jodła", "świerk"]

print("=" * 50)
print(nazwa_powierzchni)
print("=" * 50)
print("Liczba drzew:", liczba_drzew)
print("Pierwsza pierśnica:", piersnice[0], "cm")      # liczymy od zera!
print("Ostatnia pierśnica:", piersnice[-1], "cm")
print("Najgrubsze drzewo:", max(piersnice), "cm")

# ---- PĘTLA FOR I WARUNEK IF ---------------------------------------------
suma_g = 0.0
grubych = 0
for d, gat in zip(piersnice, gatunki):
    g = pole_przekroju(d)
    suma_g = suma_g + g
    if d >= 30:
        grubych += 1             # to samo co: grubych = grubych + 1
    print(f"  {gat:8s} d = {d:5.1f} cm   g = {g:.4f} m²   -> {klasa_grubosci(d)}")

pole_ha = math.pi * promien_powierzchni ** 2 / 10_000   # m² -> ha
print(f"Suma pól przekroju: {suma_g:.3f} m²")
print(f"Pole powierzchni:   {pole_ha:.3f} ha")
print(f"G na hektar:        {suma_g / pole_ha:.1f} m²/ha")
print(f"Drzew o d >= 30 cm: {grubych}")

# ---- ARGUMENT Z KONSOLI (sys.argv) --------------------------------------
# sys.argv to lista: [nazwa_programu, argument1, argument2, ...]
if len(sys.argv) > 1:
    plik = Path(sys.argv[1])
    if plik.exists():
        mb = plik.stat().st_size / 1024 / 1024
        print(f"\nPodałeś plik: {plik.name}, rozmiar {mb:.1f} MB")
        if plik.suffix.lower() in (".las", ".laz"):
            print("To jest chmura punktów - zajmiemy się nią w lekcji 3.")
    else:
        print(f"\nNie ma pliku: {plik}")
else:
    print("\n(Możesz też podać plik: python rozwiazanie_01_podstawy.py plik.laz)")
