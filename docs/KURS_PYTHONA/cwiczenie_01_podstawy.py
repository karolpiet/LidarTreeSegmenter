"""
LEKCJA 1 - ĆWICZENIE: podstawy Pythona
======================================

Uzupełnij miejsca oznaczone TODO. Program działa także przed
uzupełnieniem - wtedy w miejscach TODO wypisuje podpowiedź.

Uruchomienie:
    python cwiczenie_01_podstawy.py
"""

import math
import sys
from pathlib import Path


def pole_przekroju(d_cm):
    """Pierśnicowe pole przekroju g [m²] z pierśnicy d [cm]."""
    # TODO 1: zamień d_cm na metry i zwróć π/4 · d²
    #         Podpowiedź: math.pi, potęga to **, wynik oddajesz słowem return
    print("   [TODO 1] uzupełnij funkcję pole_przekroju()")
    return 0.0


def klasa_grubosci(d_cm):
    """Zwraca nazwę klasy grubości."""
    # TODO 2: dopisz warunki if / elif / else:
    #         d < 7 -> "nalot / podrost", d < 20 -> "drągowina",
    #         d < 35 -> "drzewostan średni", inaczej "drzewostan dojrzały"
    return "? (TODO 2)"


piersnice = [32.5, 41.0, 18.2, 55.4, 6.3, 27.9]
gatunki = ["świerk", "buk", "świerk", "buk", "jodła", "świerk"]
promien_powierzchni = 12.62

print("Liczba drzew:", len(piersnice))
# TODO 3: wypisz pierwszą i ostatnią pierśnicę oraz największą (max)
print("   [TODO 3] wypisz piersnice[0], piersnice[-1] i max(piersnice)")

suma_g = 0.0
grubych = 0
for d, gat in zip(piersnice, gatunki):
    g = pole_przekroju(d)
    suma_g = suma_g + g
    # TODO 4: jeśli d >= 30, zwiększ licznik grubych o 1
    print(f"  {gat:8s} d = {d:5.1f} cm   g = {g:.4f} m²   -> {klasa_grubosci(d)}")

pole_ha = math.pi * promien_powierzchni ** 2 / 10_000
print(f"Suma pól przekroju: {suma_g:.3f} m²")
print(f"G na hektar:        {suma_g / pole_ha:.1f} m²/ha")
print(f"Drzew o d >= 30 cm: {grubych}")

# TODO 5: jeśli podano plik w konsoli (len(sys.argv) > 1), wypisz jego
#         nazwę i rozmiar w MB:  Path(sys.argv[1]).stat().st_size / 1024 / 1024
if len(sys.argv) > 1:
    print("   [TODO 5] wypisz nazwę i rozmiar pliku", sys.argv[1])
