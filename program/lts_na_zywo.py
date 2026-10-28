"""
LidarTreeSegmenter - podgląd na żywo
=======================

Programy liczące (05, 10) w ważnych chwilach zapisują mały podgląd chmury
(najwyżej 80 tys. punktów) do pliku, który okno LidarTreeSegmenter odczytuje i rysuje:
chmura po usunięciu szumu, wysokość nad gruntem, znalezione pnie,
punkty przypisane do drzew, podział na pień / gałęzie / ulistnienie.

Plik podglądu wskazuje zmienna środowiskowa LTS_LIVE, którą ustawia
okno. Uruchomione bez okna (np. z PRZECIAGNIJ_TU_SKAN.bat) nic nie zapisują.
"""

import os
import time
from pathlib import Path

import numpy as np

MAX_PUNKTOW = 80_000


def wlaczony():
    return bool(os.environ.get("LTS_LIVE"))


def pokaz(opis, xyz, wartosci=None, rodzaj="wysokosc", okregi=None):
    """rodzaj: wysokosc (kolor wg wartosci w metrach), drzewa (kolor wg
    numeru drzewa, 0 = szary), czesci (0 nic, 1 pień, 2 gałęzie,
    3 ulistnienie). okregi: tablica Nx3 (x, y, promień) rysowana z góry."""
    cel = os.environ.get("LTS_LIVE")
    if not cel:
        return
    try:
        xyz = np.asarray(xyz)
        n = len(xyz)
        rng = np.random.default_rng(0)
        idx = rng.choice(n, MAX_PUNKTOW, replace=False) if n > MAX_PUNKTOW \
            else np.arange(n)
        w = np.zeros(len(idx), np.float32) if wartosci is None \
            else np.asarray(wartosci)[idx].astype(np.float32)
        ok = np.zeros((0, 3), np.float32) if okregi is None \
            else np.asarray(okregi, np.float32).reshape(-1, 3)
        cel = Path(cel)
        cel.parent.mkdir(parents=True, exist_ok=True)
        tmp = cel.with_name(cel.stem + "_tmp.npz")
        with open(tmp, "wb") as f:
            np.savez(f, xyz=xyz[idx].astype(np.float32), w=w, okregi=ok,
                     rodzaj=np.array(rodzaj), opis=np.array(opis),
                     punktow=np.array(n), czas=np.array(time.time()))
        os.replace(tmp, cel)
    except Exception:                                    # noqa: BLE001
        pass                   # podgląd nigdy nie może przerwać obliczeń
