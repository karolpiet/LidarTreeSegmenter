"""
LidarTreeSegmenter - KONTROLA PNIA: CZY W TYM MIEJSCU STOI WALEC?
=====================================================

Pień drzewa to walec (rurka): prosta, prawie pionowa oś, promień stały
albo łagodnie malejący ku górze, punkty na korze, a w środku pusto.
Kępa gałęzi, krzak albo kawałek korony sąsiada tak nie wygląda.

Dla każdego drzewa bierzemy WSZYSTKIE punkty skanu (nie tylko te
przypisane do drzewa) w promieniu 0,7 m od pnia, na wysokości 0,6-3,0 m
nad gruntem, i:

  1. w każdym plastrze 0,25 m szukamy okręgu (RANSAC); okrąg jest tym
     lepszy, im większą część obwodu pokrywają punkty i im mniej punktów
     leży w jego środku,
  2. sprawdzamy, czy okręgi z kolejnych plastrów składają się w jeden
     walec (środek prawie w tym samym miejscu, podobny promień),
  3. do zgodnych plastrów dopasowujemy jeden walec (oś może być lekko
     pochylona, promień może się zmieniać liniowo z wysokością),
  4. liczymy, jak dobrze punkty leżą na tym walcu:
       - w ilu plastrach walec ma punkty na korze (ciągłość),
       - jaką część obwodu widać - także w porównaniu z tym, z ilu stron
         przechodziła ścieżka skanera (skaner obszedł pień dookoła,
         a punkty są tylko z jednej strony = to nie pień),
       - ile punktów leży w środku walca (krzak ma pełny środek),
       - czy promień nie jest większy niż rozrzut punktów, na których
         stoi (łuk 100° pozwala dopasować okrąg dowolnej wielkości).

Wynik: "pien" (walec potwierdzony), "brak_pnia" (drzewo odrzucone,
nie wchodzi do sum), albo "niepewny" (zostaje, z uwagą). Do tego
pierśnica z walca na 1,3 m.
"""

import numpy as np
import pandas as pd

# --- ustawienia -----------------------------------------------------
PAS_OD, PAS_DO = 0.6, 3.0      # wysokość nad gruntem badanego odcinka [m]
PLASTER = 0.25                 # grubość plastra [m]
PROMIEN_SZUKANIA = 0.8         # punkty tak daleko od pozycji pnia [m]
SRODEK_DO = 0.30               # środek walca najdalej tyle od pozycji pnia [m]
R_MIN, R_MAX = 0.025, 0.60     # dopuszczalny promień pnia [m]
TOL_MIN = 0.012                # odległość od kory, przy której punkt
TOL_WZGL = 0.08                # „leży na korze”: max(TOL_MIN, TOL_WZGL*r)
PROB_RANSAC = 600
SASIEDZTWO = 0.30              # [m] trójki punktów do RANSAC z takiego otoczenia
MAX_PKT_PLASTRA = 2500
WNETRZE = 0.75                 # punkt bliżej środka niż tyle * r = w środku
SEKTORY = 36                   # obwód liczony w sektorach po 10°

# progi decyzji
MIN_ZGODNYCH = 5               # z 10 plastrów co najmniej tyle składa się w walec
MIN_POKRYCIE = 120.0           # mediana łuku kory w plastrze [stopnie]
MIN_POKRYCIE_OBCHODZONY = 90.0  # ... gdy punkty są ze wszystkich stron widzianych ze ścieżki
OBCHODZONY = 0.85              # (część stron widzianych ze ścieżki)
MIN_WIDOCZNE = 0.45            # część stron widzianych ze ścieżki, z których są punkty
MAX_WNETRZE = 0.35             # część punktów w środku walca
MAX_POCHYLENIE = 25.0          # stopni od pionu
MAX_ZMIANA_R = 0.06            # |zmiana promienia| [m na m wysokości]


def _okregi_z_trojek(xy, idx):
    """Okręgi przez trójki punktów (wektorowo). Zwraca cx, cy, r."""
    a, b, c = xy[idx[:, 0]], xy[idx[:, 1]], xy[idx[:, 2]]
    d = 2 * (a[:, 0] * (b[:, 1] - c[:, 1]) + b[:, 0] * (c[:, 1] - a[:, 1])
             + c[:, 0] * (a[:, 1] - b[:, 1]))
    ok = np.abs(d) > 1e-9
    d = np.where(ok, d, 1.0)
    a2, b2, c2 = (a ** 2).sum(1), (b ** 2).sum(1), (c ** 2).sum(1)
    cx = (a2 * (b[:, 1] - c[:, 1]) + b2 * (c[:, 1] - a[:, 1])
          + c2 * (a[:, 1] - b[:, 1])) / d
    cy = (a2 * (c[:, 0] - b[:, 0]) + b2 * (a[:, 0] - c[:, 0])
          + c2 * (b[:, 0] - a[:, 0])) / d
    r = np.hypot(a[:, 0] - cx, a[:, 1] - cy)
    r[~ok] = np.inf
    return cx, cy, r


def tolerancja(r):
    return np.maximum(TOL_MIN, TOL_WZGL * np.asarray(r))


def pokrycie(xy, cx, cy):
    """Maska sektorów (36 po 10°) obwodu, w których leżą punkty."""
    m = np.zeros(SEKTORY, bool)
    if len(xy):
        k = np.degrees(np.arctan2(xy[:, 1] - cy, xy[:, 0] - cx)) % 360
        m[(k // (360 / SEKTORY)).astype(int) % SEKTORY] = True
    return m


def _ocena(xy, cx, cy, r):
    """(sektory z punktami na korze, część punktów w środku, maska kory)."""
    d = np.hypot(xy[:, 0] - cx, xy[:, 1] - cy)
    kora = np.abs(d - r) < tolerancja(r)
    srodek = d < WNETRZE * r
    n_k, n_s = kora.sum(), srodek.sum()
    sekt = pokrycie(xy[kora], cx, cy).sum()
    wn = n_s / max(n_k + n_s, 1)
    return sekt, wn, kora


def _oceny(xy, cx, cy, r):
    """Dla K okręgów naraz: sektory obwodu z punktami na korze i część
    punktów w środku (macierzowo, K x n)."""
    dx = xy[None, :, 0] - cx[:, None]
    dy = xy[None, :, 1] - cy[:, None]
    d = np.hypot(dx, dy)
    kora = np.abs(d - r[:, None]) < tolerancja(r)[:, None]
    n_k = kora.sum(1)
    n_s = (d < WNETRZE * r[:, None]).sum(1)
    t = tolerancja(r)[:, None]
    n_o = ((d >= r[:, None] + t) & (d < r[:, None] + 4 * t)).sum(1)
    kat = (np.degrees(np.arctan2(dy, dx)) % 360 // (360 / SEKTORY)).astype(int)
    kod = np.where(kora, kat + SEKTORY * np.arange(len(cx))[:, None], -1)
    kod = np.unique(kod[kod >= 0])
    sekt = np.bincount(kod // SEKTORY, minlength=len(cx))
    wn = n_s / np.maximum(n_k + n_s, 1)
    cien = n_k / np.maximum(n_k + n_o / 3, 1)   # kora cienka jak skórka
    return sekt, wn * 1.0, n_k * cien


def _kasa(q):
    A = np.column_stack([q[:, 0], q[:, 1], np.ones(len(q))])
    sol, *_ = np.linalg.lstsq(A, (q ** 2).sum(1), rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    return cx, cy, np.sqrt(max(sol[2] + cx ** 2 + cy ** 2, 0))


def okrag_plastra(xy, x0, y0, rng):
    """Najlepszy okrąg w plastrze: dużo obwodu na korze, pusto w środku."""
    if len(xy) < 8:
        return None
    if len(xy) > MAX_PKT_PLASTRA:
        xy = xy[rng.choice(len(xy), MAX_PKT_PLASTRA, replace=False)]
    # trójki z sąsiedztwa: pierwszy punkt losowy, dwa kolejne w promieniu
    # SASIEDZTWO od niego - punkty jednego pnia leżą blisko siebie, więc
    # tak trafiamy w pień dużo częściej niż losując z całego plastra
    from scipy.spatial import cKDTree
    drz = cKDTree(xy)
    pierwsze = rng.integers(0, len(xy), PROB_RANSAC)
    sas = drz.query_ball_point(xy[pierwsze], SASIEDZTWO)
    idx = np.empty((PROB_RANSAC, 3), int)
    for k, (i, s_) in enumerate(zip(pierwsze, sas)):
        if len(s_) >= 3:
            idx[k] = [i] + list(rng.choice(s_, 2, replace=False))
        else:
            idx[k] = rng.integers(0, len(xy), 3)
    cx, cy, r = _okregi_z_trojek(xy, idx)
    ok = (r >= R_MIN) & (r <= R_MAX) & \
        (np.hypot(cx - x0, cy - y0) <= SRODEK_DO)
    if not ok.any():
        return None
    cx, cy, r = cx[ok], cy[ok], r[ok]
    sekt, wn, nk = _oceny(xy, cx, cy, r)
    wart = sekt * (1 - wn) ** 2 * np.minimum(1, nk / 25) * (nk >= 6)
    najl = np.argsort(-wart)[:5]
    # dopracowanie najlepszych: okrąg dopasowany do punktów ich kory
    kx, ky, kr = list(cx[najl]), list(cy[najl]), list(r[najl])
    for i in najl:
        d = np.hypot(xy[:, 0] - cx[i], xy[:, 1] - cy[i])
        q = xy[np.abs(d - r[i]) < tolerancja(r[i])]
        if len(q) >= 6:
            a, b, c = _kasa(q)
            if R_MIN <= c <= R_MAX:
                kx.append(a), ky.append(b), kr.append(c)
    kx, ky, kr = np.array(kx), np.array(ky), np.array(kr)
    sekt, wn, nk = _oceny(xy, kx, ky, kr)
    wart = sekt * (1 - wn) ** 2 * np.minimum(1, nk / 25) * (nk >= 6)
    i = int(np.argmax(wart))
    if wart[i] <= 0:
        return None
    return dict(cx=kx[i], cy=ky[i], r=kr[i], sekt=int(sekt[i]),
                wn=float(wn[i]), nk=int(nk[i]))


def zbadaj(p, h, x0, y0, sektory_sciezki=None, rng=None, drzewo=None):
    """p: (n, 3) xyz punktów wokół pnia, h: wysokość nad gruntem.
    sektory_sciezki: maska 36 sektorów, z których widać pień ze ścieżki
    (lts_sciezka.widocznosc) albo None. drzewo: numer drzewa każdego
    punktu (do sprawdzenia, czyje punkty leżą na korze walca).
    Zwraca słownik z wynikiem."""
    rng = rng or np.random.default_rng(0)
    gr = np.arange(PAS_OD, PAS_DO - 1e-6, PLASTER)
    wyn = dict(werdykt="brak_pnia", powod="", d_walca_m=np.nan,
               zgodnych=0, plastrow=len(gr), pokrycie_deg=0.0,
               widoczne=np.nan, wnetrze=np.nan, pochylenie_deg=np.nan,
               zmiana_r_m_na_m=np.nan, srodek_x=np.nan, srodek_y=np.nan,
               wlasciciel=-1, udzial_wlasciciela=np.nan)
    blisko = np.hypot(p[:, 0] - x0, p[:, 1] - y0) < PROMIEN_SZUKANIA
    p, h = p[blisko], h[blisko]
    drzewo = np.zeros(len(p), int) if drzewo is None else \
        np.asarray(drzewo)[blisko]
    okr = []
    for g in gr:
        w = (h >= g) & (h < g + PLASTER)
        o = okrag_plastra(p[w, :2], x0, y0, rng)
        if o is not None:
            o["h"] = g + PLASTER / 2
            okr.append(o)
    if len(okr) < 3:
        wyn["powod"] = "w pasie 0,6-3 m nie ma okręgów pnia"
        return wyn
    # zgoda plastrów: dla każdego okręgu - ile innych do niego pasuje
    C = np.array([[o["cx"], o["cy"], o["r"], o["h"], o["sekt"]] for o in okr])

    def zgodne(i):
        dc = np.hypot(C[:, 0] - C[i, 0], C[:, 1] - C[i, 1])
        dr = np.abs(C[:, 2] - C[i, 2]) / C[i, 2]
        return (dc < np.maximum(0.04, 0.35 * C[i, 2])) & (dr < 0.3)
    zg = [zgodne(i) for i in range(len(C))]
    ile = np.array([z.sum() + 0.01 * C[i, 4] for i, z in enumerate(zg)])
    sel = zg[int(np.argmax(ile))]
    Z = C[sel]
    if len(Z) < 3:
        wyn["powod"] = "okręgi z kolejnych plastrów nie składają się w walec"
        wyn["zgodnych"] = int(len(Z))
        return wyn
    # walec: środek i promień liniowo z wysokością (ważone łukiem)
    wg = Z[:, 4]
    fx = np.polyfit(Z[:, 3], Z[:, 0], 1, w=wg)
    fy = np.polyfit(Z[:, 3], Z[:, 1], 1, w=wg)
    fr = np.polyfit(Z[:, 3], Z[:, 2], 1, w=wg) if np.ptp(Z[:, 3]) > 0.4 \
        else np.array([0.0, np.average(Z[:, 2], weights=wg)])
    # ocena walca na wszystkich plastrach
    zgodnych, luk, sekt_suma = 0, [], np.zeros(SEKTORY, bool)
    n_kora = n_srodek = 0
    czyje = []
    for g in gr:
        hm = g + PLASTER / 2
        w = (h >= g) & (h < g + PLASTER)
        cx, cy = np.polyval(fx, hm), np.polyval(fy, hm)
        r = max(np.polyval(fr, hm), R_MIN)
        q = p[w, :2]
        d = np.hypot(q[:, 0] - cx, q[:, 1] - cy)
        kora = np.abs(d - r) < tolerancja(r)
        n_kora += kora.sum()
        czyje.append(drzewo[w][kora])
        n_srodek += (d < WNETRZE * r).sum()
        m = pokrycie(q[kora], cx, cy)
        luk.append(m.sum() * 360 / SEKTORY)
        if kora.sum() >= 6 and m.sum() >= 5:
            zgodnych += 1
            sekt_suma |= m
    czyje = np.concatenate(czyje)
    if len(czyje):
        u, n = np.unique(czyje, return_counts=True)
        wyn["wlasciciel"] = int(u[np.argmax(n)])
        wyn["udzial_wlasciciela"] = float(n.max() / n.sum())
    r13 = max(np.polyval(fr, 1.3), R_MIN)
    poch = np.degrees(np.arctan(np.hypot(fx[0], fy[0])))
    wyn.update(zgodnych=zgodnych, pokrycie_deg=float(np.median(luk)),
               wnetrze=float(n_srodek / max(n_kora + n_srodek, 1)),
               pochylenie_deg=float(poch), zmiana_r_m_na_m=float(fr[0]),
               d_walca_m=float(2 * r13), srodek_x=float(np.polyval(fx, 1.3)),
               srodek_y=float(np.polyval(fy, 1.3)))
    if sektory_sciezki is not None and sektory_sciezki.sum() >= 6:
        wyn["widoczne"] = float((sekt_suma & sektory_sciezki).sum()
                                / sektory_sciezki.sum())
    # decyzja
    powody = []
    if zgodnych < MIN_ZGODNYCH:
        powody.append(f"walec tylko w {zgodnych} z {len(gr)} plastrów")
    prog = MIN_POKRYCIE_OBCHODZONY if (np.isfinite(wyn["widoczne"]) and
                                       wyn["widoczne"] >= OBCHODZONY) \
        else MIN_POKRYCIE
    if wyn["pokrycie_deg"] < prog:
        powody.append(f"kora widoczna na {wyn['pokrycie_deg']:.0f}° obwodu"
                      " (promień niepewny)")
    if np.isfinite(wyn["widoczne"]) and wyn["widoczne"] < MIN_WIDOCZNE:
        powody.append(f"skaner obszedł pień, a punkty są tylko z "
                      f"{wyn['widoczne']*100:.0f}% stron")
    if wyn["wnetrze"] > MAX_WNETRZE:
        powody.append(f"{wyn['wnetrze']*100:.0f}% punktów w środku walca")
    if poch > MAX_POCHYLENIE:
        powody.append(f"oś pochylona o {poch:.0f}°")
    if abs(fr[0]) > MAX_ZMIANA_R:
        powody.append(f"promień zmienia się o {fr[0]*100:+.0f} cm na metr")
    wyn["powod"] = "; ".join(powody)
    wyn["werdykt"] = "pien" if not powody else "brak_pnia"
    return wyn


# ======================================================================
# CAŁY SKAN
# ======================================================================
MIN_UDZIAL_WLASCICIELA = 0.6   # tyle punktów kory walca musi należeć do
                               # innego drzewa, żeby uznać pień za cudzy
POPRAW_D_POKRYCIE = 200.0      # pierśnica z walca zastępuje pomiar, gdy
POPRAW_D_ROZNICA = 0.30        # walec widać na tylu stopniach obwodu, a
                               # pomiary różnią się o więcej niż tyle
POLE_WYSOKOSCI = ("wys_nad_grunt", "hag", "HeightAboveGround")


def _ocena_wyniku(w):
    return (w["werdykt"] == "pien", w["zgodnych"] * w["pokrycie_deg"])


def kontrola_skanu(xyz, hag, drzewo, czesc, drzewa, sektory=None,
                   podszyt=4, wypisz=print):
    """xyz, hag, drzewo, czesc: punkty skanu (czesc - klasa z kroku 2,
    punkty podszytu są pomijane). drzewa: DataFrame z kolumnami nr i listą
    kandydatów na środek pnia (kolumny x, y, x2, y2, x3, y3 - puste
    pomijane). sektory: {nr: maska 36 sektorów widzianych ze ścieżki}.
    Zwraca DataFrame: nr, werdykt (pien / brak_pnia / duplikat), powod,
    d_walca_m, ..."""
    from scipy.spatial import cKDTree
    m = (hag > PAS_OD - 0.05) & (hag < PAS_DO + 0.05)
    if czesc is not None:
        m &= czesc != podszyt
    xyz, hag, drzewo = xyz[m], hag[m], drzewo[m]
    drz = cKDTree(xyz[:, :2])
    wyniki = []
    for _, t in drzewa.iterrows():
        kand = [(t[a], t[b]) for a, b in (("x", "y"), ("x2", "y2"),
                                          ("x3", "y3"))
                if a in t and np.isfinite(t[a]) and np.isfinite(t[b])]
        najl = None
        for x0, y0 in kand:
            idx = drz.query_ball_point([x0, y0], PROMIEN_SZUKANIA)
            w = zbadaj(xyz[idx], hag[idx], x0, y0,
                       None if sektory is None else sektory.get(int(t.nr)),
                       np.random.default_rng(int(t.nr)), drzewo[idx])
            if najl is None or _ocena_wyniku(w) > _ocena_wyniku(najl):
                najl = w
        if najl is None:
            najl = zbadaj(np.zeros((0, 3)), np.zeros(0), 0, 0)
            najl["powod"] = "brak pozycji pnia"
        najl["nr"] = int(t.nr)
        wyniki.append(najl)
    W = pd.DataFrame(wyniki)
    W["duplikat_drzewa"] = np.nan
    # ten sam walec u dwóch drzew = jeden pień policzony dwa razy;
    # zostaje drzewo, do którego należą punkty kory
    nr_wszystkie = set(W.nr)
    p = W[W.werdykt == "pien"]
    xy = p[["srodek_x", "srodek_y"]].to_numpy(float)
    R = p.d_walca_m.to_numpy(float) / 2
    n = p.nr.to_numpy()
    wl = dict(zip(W.nr, W.wlasciciel))
    ud = dict(zip(W.nr, W.udzial_wlasciciela))
    for i, a in enumerate(n):
        D = np.hypot(xy[:, 0] - xy[i, 0], xy[:, 1] - xy[i, 1])
        for j in np.flatnonzero(D < np.maximum(0.05, (R[i] + R) / 2)):
            b = n[j]
            if b == a:
                continue
            if wl[a] == b or (wl[a] != a and wl[b] != b and a > b):
                W.loc[W.nr == a, "duplikat_drzewa"] = b
    # pień należy w większości do innego drzewa z tabeli, którego walec
    # stoi w tym samym miejscu albo którego nie dało się sprawdzić
    for i, w in W[W.werdykt == "pien"].iterrows():
        b = w.wlasciciel
        if b != w.nr and b in nr_wszystkie and pd.isna(w.duplikat_drzewa) \
                and ud[w.nr] >= MIN_UDZIAL_WLASCICIELA:
            wb = W[W.nr == b].iloc[0]
            if wb.werdykt != "pien" or np.hypot(
                    wb.srodek_x - w.srodek_x, wb.srodek_y - w.srodek_y) \
                    < max(0.05, w.d_walca_m / 2):
                W.loc[i, "duplikat_drzewa"] = b
    dup = W.duplikat_drzewa.notna() & (W.werdykt == "pien")
    W.loc[dup, "werdykt"] = "duplikat"
    W.loc[dup, "powod"] = [f"ten sam pień co drzewo {int(b)}"
                           for b in W.loc[dup, "duplikat_drzewa"]]
    wypisz(f"         pień potwierdzony: {(W.werdykt == 'pien').sum()}, "
           f"brak pnia: {(W.werdykt == 'brak_pnia').sum()}, "
           f"duplikaty: {dup.sum()}")
    return W
