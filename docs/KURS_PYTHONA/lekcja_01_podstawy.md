# Lekcja 1 – Podstawy Pythona: zmienne, listy, pętle, warunki, funkcje

**Czego się nauczysz:** zapisywać liczby i teksty w zmiennych, trzymać wiele wartości
na liście, powtarzać czynność pętlą `for`, podejmować decyzje warunkiem `if`,
pisać własne funkcje i uruchamiać program z konsoli z argumentem.

**Pliki:** `cwiczenie_01_podstawy.py`, `rozwiazanie_01_podstawy.py`

---

## Najpierw po leśnemu

Wyobraź sobie, że idziesz na powierzchnię próbną z klupą i notesem.

- **Zmienna** to jedna rubryka w notesie z nazwą: `promien_powierzchni = 12.62`.
- **Lista** to kolumna w manualiku – pierśnice wszystkich drzew po kolei:
  `[32.5, 41.0, 18.2, ...]`.
- **Pętla `for`** to chodzenie od drzewa do drzewa: „dla każdego drzewa zmierz i zapisz”.
- **Warunek `if`** to decyzja: „jeśli pierśnica ≥ 7 cm, to klupuj, w przeciwnym razie pomiń”.
- **Funkcja** to przepis, którego nauczyłeś się raz i stosujesz zawsze, np. „pole przekroju
  z pierśnicy: g = π/4 · d²”. Podajesz pierśnicę, dostajesz pole.

Program to po prostu taki notes z przepisami – tylko że wykonuje je komputer, bez pomyłek
i w ułamku sekundy.

---

## Zmienne i typy

```python
nazwa_powierzchni = "Powierzchnia próbna nr 7"   # tekst  (str)  – w cudzysłowie
promien_powierzchni = 12.62                      # liczba z kropką (float)
liczba_drzew = 6                                 # liczba całkowita (int)
pomierzona = True                                # prawda / fałsz (bool)
```

Znak `=` **nie** znaczy „równa się” jak w matematyce. Znaczy: **„włóż do szuflady
o tej nazwie”**. Dlatego można napisać `suma = suma + g` – „weź to, co jest w szufladzie
`suma`, dodaj `g` i włóż z powrotem”. Skrót: `suma += g`.

Działania: `+  -  *  /`, potęga `**` (np. `d ** 2`), dzielenie całkowite `//`, reszta `%`.

## Listy

```python
piersnice = [32.5, 41.0, 18.2, 55.4, 6.3, 27.9]
print(piersnice[0])     # 32.5 – PIERWSZY element ma numer 0 (!)
print(piersnice[-1])    # 27.9 – ujemny numer liczy od końca
print(len(piersnice))   # 6    – ile elementów
print(max(piersnice))   # 55.4
piersnice.append(22.0)  # dopisz na końcu
```

Python liczy **od zera**. Pierwsze drzewo to `[0]`, drugie `[1]`. Do tego trzeba się
przyzwyczaić – będzie wszędzie.

## Pętla `for`

```python
for d in piersnice:
    print("pierśnica", d)
print("koniec")          # to już poza pętlą – brak wcięcia
```

Linie **wcięte o 4 spacje** pod `for` wykonują się dla każdego elementu.
Pierwsza linia bez wcięcia kończy pętlę.

`zip` pozwala iść po dwóch listach naraz – jak po dwóch kolumnach manualika:

```python
for d, gat in zip(piersnice, gatunki):
    print(gat, d)
```

## Warunek `if`

```python
if d < 7:
    print("nalot / podrost")
elif d < 20:              # elif = "a jeśli nie, to sprawdź jeszcze to"
    print("drągowina")
else:                     # else = "we wszystkich pozostałych przypadkach"
    print("starsze")
```

Porównania: `<  >  <=  >=  ==` (równe – **dwa** znaki `=`!), `!=` (różne).
Łączenie: `and`, `or`, `not`.

## Funkcje

```python
def pole_przekroju(d_cm):
    """Pierśnicowe pole przekroju g [m²] z pierśnicy d [cm]."""
    d_m = d_cm / 100
    return math.pi / 4 * d_m ** 2

g = pole_przekroju(32.5)     # g = 0.083
```

- `def` – „definiuję przepis”, potem nazwa i w nawiasie to, co przepis dostaje.
- Tekst w potrójnym cudzysłowie to opis funkcji (dla ludzi).
- `return` – co przepis oddaje.

## Moduły – gotowe skrzynki z narzędziami

```python
import math          # matematyka: math.pi, math.sqrt ...
import sys           # system: m.in. argumenty z konsoli
```

W kolejnych lekcjach będziemy importować biblioteki do chmur punktów:
`numpy`, `laspy`, `scipy`, `pandas`, `matplotlib`.

## Argumenty z konsoli – `sys.argv`

Gdy wpiszesz `python program.py plik.laz 17`, Python zapisuje to na liście `sys.argv`:

```python
sys.argv[0]   # 'program.py'   – nazwa programu
sys.argv[1]   # 'plik.laz'     – pierwszy argument
sys.argv[2]   # '17'           – drugi argument (to TEKST, na liczbę: int(sys.argv[2]))
```

Zawsze sprawdzamy, czy argument podano – inaczej `sys.argv[1]` skończy się błędem `IndexError`:

```python
if len(sys.argv) < 2:
    sys.exit("BŁĄD: podaj plik .laz")
```

---

## Prawdziwy kod LidarTreeSegmenter – linijka po linijce

Fragment z `program\10_pien_galezie_liscie.py` (krok 1 – wczytanie chmury). Gdy w pliku
nie ma wysokości nad gruntem, LidarTreeSegmenter liczy ją od dołu każdego drzewa:

```python
POLA_WYSOKOSCI = ("wys_nad_grunt", "hag", "HeightAboveGround")
...
    pole_wys = next((p for p in POLA_WYSOKOSCI if p in pola), None)
    if pole_wys:
        h = np.asarray(las[pole_wys], dtype=np.float64)
        print(f"         wysokosc nad gruntem z pola: {pole_wys}")
    else:
        # Bez gruntu: liczymy od najnizszego punktu kazdego drzewa.
        # Dla pomiaru pnia wystarczy, ale wysokosci beda przyblizone.
        h = np.zeros(len(xyz))
        for t in np.unique(drzewo):
            m = drzewo == t
            h[m] = xyz[m, 2] - np.percentile(xyz[m, 2], 0.5)
```

| linia | co robi, po ludzku |
|---|---|
| `POLA_WYSOKOSCI = (...)` | zmienna z trzema nazwami, pod którymi różne programy zapisują wysokość nad gruntem. Nawiasy okrągłe to **krotka** – lista, której nie można zmieniać. Wielkie litery = umowa: „to stała, nie zmieniaj”. |
| `pole_wys = next((p for p in ... if p in pola), None)` | „przejrzyj po kolei te trzy nazwy i daj mi **pierwszą**, która jest w pliku; jak żadnej nie ma – daj `None`” (`None` = nic, pusto). |
| `if pole_wys:` | warunek: „jeśli coś znaleziono”. Pusty wynik (`None`) liczy się jak fałsz. |
| `h = np.asarray(las[pole_wys], ...)` | weź z pliku kolumnę wysokości (o tym w lekcji 3). |
| `print(f"... {pole_wys}")` | wypisz komunikat. Litera `f` przed cudzysłowem pozwala wstawić zmienną w `{ }`. |
| `else:` | w przeciwnym razie (nie ma wysokości w pliku)… |
| `# Bez gruntu: ...` | komentarz dla człowieka. |
| `h = np.zeros(len(xyz))` | przygotuj „pustą kolumnę” zer, po jednym na każdy punkt. |
| `for t in np.unique(drzewo):` | **pętla po drzewach**: `np.unique` daje listę różnych numerów drzew. |
| `m = drzewo == t` | dla każdego punktu: czy należy do drzewa `t`? (Prawda/fałsz – lekcja 2.) |
| `h[m] = xyz[m, 2] - np.percentile(...)` | wysokość punktów tego drzewa = ich `z` minus prawie-najniższy punkt drzewa (percentyl 0,5% – żeby jeden zabłąkany punkt pod ziemią nie zepsuł wyniku). |

Widzisz? Zmienne, `if`/`else`, pętla `for` – dokładnie to, czego uczymy się w tej lekcji.
Prawdziwy program składa się z tych samych klocków.

---

## Uruchom rozwiązanie

```
python rozwiazanie_01_podstawy.py
```

Zobaczysz mniej więcej:

```
==================================================
Powierzchnia próbna nr 7
==================================================
Liczba drzew: 6
Pierwsza pierśnica: 32.5 cm
Ostatnia pierśnica: 27.9 cm
Najgrubsze drzewo: 55.4 cm
  świerk   d =  32.5 cm   g = 0.0830 m²   -> drzewostan średni
  buk      d =  41.0 cm   g = 0.1320 m²   -> drzewostan dojrzały
  ...
Suma pól przekroju: 0.546 m²
Pole powierzchni:   0.050 ha
G na hektar:        10.9 m²/ha
Drzew o d >= 30 cm: 3
```

Spróbuj też z argumentem – podaj dowolny plik `.laz` (przeciągnij go do konsoli):

```
python rozwiazanie_01_podstawy.py ..\..\wyniki\SKAN\02_CHMURY\SKAN_czesci.laz
```

---

## Ćwiczenie

Otwórz `cwiczenie_01_podstawy.py` i uzupełnij miejsca **TODO**:

1. **TODO 1** – funkcja `pole_przekroju(d_cm)`: zamień centymetry na metry i oddaj π/4 · d².
2. **TODO 2** – funkcja `klasa_grubosci(d_cm)`: warunki `if / elif / else`.
3. **TODO 3** – wypisz pierwszą, ostatnią i największą pierśnicę.
4. **TODO 4** – w pętli policz drzewa o pierśnicy co najmniej 30 cm.
5. **TODO 5** – jeśli podano plik w konsoli, wypisz jego nazwę i rozmiar w MB.

Uruchamiaj program po każdej zmianie: `python cwiczenie_01_podstawy.py`.
Zanim uzupełnisz TODO, program i tak działa – w tych miejscach wypisuje podpowiedź.

**Dla chętnych:** dopisz do listy siódme drzewo (`piersnice.append(...)`,
`gatunki.append(...)`) i zobacz, jak zmienia się G na hektar.

## Podpowiedź

- Centymetry na metry: `d_m = d_cm / 100`. π to `math.pi`, kwadrat to `** 2`.
- Funkcja musi kończyć się `return wynik` – inaczej oddaje `None`.
- Licznik w pętli: `if d >= 30:` a pod spodem (wcięte!) `grubych += 1`.
- Rozmiar pliku: `Path(sys.argv[1]).stat().st_size` daje bajty; podziel przez `1024 * 1024`.
- Wynik do sprawdzenia: suma pól przekroju = **0,546 m²**, drzew grubych = **3**.

## Podsumowanie

- zmienna = szuflada z nazwą, `=` to „włóż”,
- lista `[ ]` liczona od **zera**,
- `for` + wcięcie = powtarzaj; `if / elif / else` = decyduj,
- `def nazwa(...): ... return` = własny przepis,
- `sys.argv` = to, co wpisałeś w konsoli po nazwie programu.
