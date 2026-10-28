# Kurs Pythona z programem LidarTreeSegmenter – spis treści

Kurs dla leśnika, który zaczyna od zera: Python, chmury punktów LiDAR i algorytmy,
na których działa LidarTreeSegmenter – na prawdziwym kodzie i prawdziwych skanach.

**Zacznij od:** [00_JAK_ZACZAC.md](00_JAK_ZACZAC.md) – konsola, uruchamianie programów,
edytory, czytanie błędów, mały plik do ćwiczeń.

| nr | lekcja | czego się uczysz (Python) | o co chodzi w lesie / w LidarTreeSegmenter |
|---|---|---|---|
| 1 | [Podstawy Pythona](lekcja_01_podstawy.md) | zmienne, listy, `for`, `if`, funkcje, `sys.argv` | pole przekroju, klasy grubości, G/ha z manualika |
| 2 | [numpy – chmura jako tablica](lekcja_02_numpy.md) | tablica N × 3, wycinanie, min/max/średnia, maski | punkty x, y, z; plaster na wysokości pierśnicy |
| 3 | [Czytanie .las / .laz](lekcja_03_laspy.md) | `laspy`, nagłówek, pola dodatkowe, `np.unique`, `np.bincount` | numer drzewa, część drzewa, wysokość nad gruntem |
| 4 | [Wysokość nad gruntem](lekcja_04_wysokosc.md) | siatka, `np.minimum.at`, zapis nowego `.laz` | model terenu, plaster 1,3 m ± 5 cm |
| 5 | [Przerzedzanie voxelami](lekcja_05_voxele.md) | `np.floor`, `np.unique(return_index/inverse)`, `del` | jak liczyć 15 mln punktów bez czekania godzinami |
| 6 | [Okrąg i pierśnica](lekcja_06_okrag.md) | `np.linalg.lstsq`, własny moduł, słownik | metoda Kåsy, DBH = 2r, kontrola jakości |
| 7 | [Sąsiedzi i szum](lekcja_07_sasiedzi.md) | `cKDTree`, `query_ball_point`, liczenie partiami | filtr szumu SOR, gęstość punktów |
| 8 | [Graf i Dijkstra](lekcja_08_graf.md) | macierz rzadka, `dijkstra`, pętla `while` | „droga po drewnie”, podział chmury na drzewa |
| 9 | [Tabela i Excel](lekcja_09_tabela.md) | `pandas`, `DataFrame`, `groupby`, `to_excel` | g, V = g · h · f (świerk 0,47, buk 0,51), G i V na ha |
| 10 | [Obrazki](lekcja_10_obrazki.md) | `matplotlib`, `scatter`, próbka losowa, `savefig` | mapa skanu, karta drzewa z boku i z góry |

## Pliki w folderze

```
KURS_PYTHONA\
  00_JAK_ZACZAC.md            jak uruchamiać, edytować, czytać błędy
  SPIS_TRESCI.md              ten plik
  OTWORZ_KONSOLE_TUTAJ.bat    konsola w folderze kursu (dwuklik)
  lekcja_NN_temat.md          tekst lekcji
  cwiczenie_NN_temat.py       ćwiczenie z miejscami TODO
  rozwiazanie_NN_temat.py     działające rozwiązanie
  kurs_wspolne.py             wspólne funkcje (lekcje 6–10)
  dane_testowe\
    make_maly_las.py          wycina mały kawałek skanu do ćwiczeń
  obrazki\                    ilustracje do lekcji
  wyniki_kursu\               tu programy zapisują swoje wyniki (powstaje sam)
```

## Na czym ćwiczyć

| plik | skąd | co ma | najlepszy do lekcji |
|---|---|---|---|
| `<skan>_segmenty.laz` | `LidarTreeSegmenter\wyniki\<skan>\02_CHMURY\` | `treeID_pred`, `wys_nad_grunt` | 3, 4, 5, 7 |
| `<skan>_czesci.laz` | jw. | `treeID`, `czesc`, `p_drewno` | 3, 6, 8, 9, 10 |
| surowy skan `.laz` | ze skanera | tylko x, y, z (i np. intensywność) | 2, 3, 4, 5, 7 (pozostałe działają w uproszczeniu) |
| mały wycinek | `dane_testowe\make_maly_las.py` | to samo co oryginał, ok. 1 mln punktów | wszystkie – szybko |

## Biblioteki

Kurs używa tych samych bibliotek co LidarTreeSegmenter (są już zainstalowane, jeśli LidarTreeSegmenter działa):

```
python -m pip install laspy lazrs numpy pandas scipy scikit-learn matplotlib openpyxl
```
