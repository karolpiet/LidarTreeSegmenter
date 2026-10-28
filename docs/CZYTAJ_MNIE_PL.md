# LidarTreeSegmenter

Polska wersja opisu (angielski: README.md w głównym folderze). Pracownia do segmentacji drzew z chmury punktów LiDAR (TLS/MLS). Wykrywanie drzew korzysta z `tree_segmenter_tool\02_detect_trees.py`, który jest dołączony w tym repozytorium.

## Najprościej: okno LidarTreeSegmenter

1. **Raz na początku:** kliknij dwa razy `ZAINSTALUJ_RAZ.bat`. Doinstaluje potrzebne biblioteki.
2. **Za każdym razem:** kliknij dwa razy `LidarTreeSegmenter_PL.bat`, wybierz skan (`.laz` albo `.las`) i kliknij Start. Możesz też upuścić skan myszką na `LidarTreeSegmenter_PL.bat`, wtedy liczenie zacznie się samo.
3. W oknie widać postęp każdego etapu, czas, liczbę drzew, udział pnia, gałęzi i ulistnienia oraz miąższość na hektar. Zakładka **Podgląd na żywo** pokazuje chmurę w trakcie liczenia (z góry i z boku): po usunięciu szumu, wysokość nad gruntem, znalezione pnie jako czerwone okręgi, punkty przypisane do drzew, a na końcu pień, gałęzie i ulistnienie. Zakładka **Obrazki drzew** pokazuje obrazki w miarę jak powstają. Na końcu przyciski otwierają folder wyników, obrazki, raport Excel i widok 3D, a **Sprawdź drzewa** i **Przelicz raport** służą do przeglądania drzew (opis niżej).

4. **Przed Start** wybierz dwie rzeczy (okno zapamiętuje wybór dla każdego skanu):
   - **Drzewostan:** `młody` (pierśnice ok. 8–20 cm), `dojrzały` (grubsze) albo `automatycznie` (program sam wybiera po medianie pierśnic). Od klasy zależy najmniejsza i największa szukana średnica pnia, wysokość, poniżej której gruby obiekt uznaje się za krzew, i zasięg podszytu. Liczby są w `klasy_drzewostanu.csv` (Excel albo Notatnik) i możesz je zmienić.
   - **Gatunek:** `rozpoznaj z kształtu`, `same świerki` albo `same buki`. Gdy wiesz, że na powierzchni rośnie jeden gatunek (np. S4v to same świerki), wybierz go. Rozpoznawanie z kształtu w gęstym drzewostanie myli świerka z bukiem, bo korony się zasłaniają.

Stary sposób dalej działa: upuść skan na `PRZECIAGNIJ_TU_SKAN.bat` (czarne okno zamiast graficznego).

### Kolejka na noc (wiele skanów naraz)

Kliknij **Kolejka na noc…** (albo upuść na `LidarTreeSegmenter_PL.bat` kilka skanów albo cały folder). W okienku:

1. **Dodaj pliki…** albo **Dodaj folder…** (z podfolderami). Strzałki zmieniają kolejność.
2. Zaznacz skany (Ctrl albo Shift + klik), wybierz drzewostan i gatunek, kliknij **Ustaw**. Każdy skan może mieć inne ustawienia.
3. **Pomijaj etapy już policzone**: skan liczony wcześniej nie jest liczony od nowa, robi się tylko to, czego brakuje albo co się zmieniło (np. nowy plik sprawdzenia albo pomiaru terenowego). Zmiana drzewostanu albo gatunku liczy skan ponownie od etapu 2.
4. **Po zakończeniu**: nic, uśpij albo wyłącz komputer. Przed uśpieniem albo wyłączeniem jest minuta odliczania z przyciskiem Anuluj.
5. **Start kolejki.**

Skany liczą się po kolei, a główne okno pokazuje bieżący skan („Kolejka: skan 3 z 8”). Błąd jednego skanu nie zatrzymuje reszty. Podczas liczenia komputer sam się nie uśpi. Po każdym skanie zapisuje się zestawienie `wyniki\KOLEJKA_<data>_<godzina>.xlsx`: jeden wiersz na powierzchnię (stan, czas, drzewostan, gatunek, powierzchnia, liczba drzew, N/ha, Dg, wysokość Loreya, G/ha, miąższość na powierzchni i V/ha, krzewy, złomy, opis błędu) i średnia z policzonych. Dziennik każdego skanu jest w jego `05_DZIENNIK`.

### Sprawdzanie drzew (do wyników „na czysto”)

Szybka wersja to sam Start: program decyduje sam. Gdy wynik ma być pewny (np. do zlecenia), przejrzyj drzewa:

1. Po liczeniu kliknij **Sprawdź drzewa**. Widok 3D otworzy się w przeglądarce od razu w trybie sprawdzania.
2. Program pokazuje drzewa po kolei, najpierw podejrzane (krzewy, złomy, niepewne, bez pierśnicy). Bieżące drzewo jest podświetlone na tle całego skanu, obok jest jego obrazek (kliknięcie powiększa) i dane.
3. Klawisze: **1** drzewo OK, **2** krzak, **3** złom, **4** świerk, **5** buk, **→** pomiń, **←** wstecz. Gatunek możesz dodać do decyzji (np. 1, a potem 4).
4. Decyzje zapisują się w przeglądarce na bieżąco, więc możesz przerwać i wrócić. Na koniec kliknij **Zapisz sprawdzenie** i zapisz plik `<skan>_sprawdzenie.csv` w folderze `wyniki\<skan>\01_RAPORT`.
5. W oknie LidarTreeSegmenter kliknij **Przelicz raport**. Liczy się tylko raport i widok 3D (kilka sekund), bez liczenia chmury od nowa.

Twoje decyzje mają pierwszeństwo przed programem: krzak wypada z sum, złom liczy się z miąższości zmierzonej strzały, „drzewo OK” wraca do wyników. W Excelu takie drzewa mają „tak” w kolumnie „Sprawdzone ręcznie”. Plik sprawdzenia to zwykły CSV (`nr;decyzja;gatunek`), można go też poprawić w Excelu.

### Pomiar terenowy (dopasowanie do drzew zmierzonych Garminem)

Gdy masz pomiar kilku drzew (np. 5 ze środka powierzchni), LidarTreeSegmenter sam znajdzie je w skanie, obróci i przesunie skan do współrzędnych terenowych i porówna pierśnice.

1. Skopiuj `SZABLON_pomiar.csv` jako `<skan>_pomiar.csv` (np. `_S4v__r20_pomiar.csv`) i wpisz drzewa: `nr;szerokosc;dlugosc;piersnica_cm;gatunek;wysokosc_m`. Gatunek i wysokość są nieobowiązkowe. Współrzędne mogą być w stopniach (`49.61234`, `49,61234`) albo jak na Garminie (`N49 36.740`). Zamiast stopni możesz podać `x;y;epsg` (np. EPSG 2180). Można też dać punkty z Garmina jako `<skan>_pomiar.gpx` (nazwa punktu = numer drzewa), a w CSV wpisać tylko numer i pierśnicę. Plik `.xlsx` z tymi kolumnami też działa.
2. Połóż plik w `wyniki\<skan>\01_RAPORT` albo obok pliku skanu i kliknij **Przelicz raport** (albo Start).
3. Wynik:
   - arkusz **„Pomiar terenowy”** w Excelu (które drzewo ze skanu to które z terenu, różnica pierśnic, odchyłka GPS w metrach, obrót skanu, ocena dopasowania: dobre / niepewne / słabe);
   - `01_RAPORT\<skan>_georef.gpkg`: wszystkie warstwy GeoPackage w układzie terenowym (UTM albo EPSG 2180), plus warstwy `pomiar_terenowy` i `odchylki_gps` do QGIS.

Układ wynikowy to strefa UTM z położenia drzew. Inny układ podasz tak: `python program\30_raport.py wyniki\<skan> --epsg 2180`.

**Żeby dopasowanie wyszło:** Garmin myli się o 3–5 m i to wystarcza do orientacji tylko wtedy, gdy drzewa są dobrze dobrane. Z próby na S2j (5 drzew, błąd GPS 2 m): drzewa skupione przy środku dawały dobry obrót w 32 na 40 prób, a rozrzucone w odległości 6–14 m od środka w 39 na 40 (mediana błędu obrotu 3,5°). Przy błędzie 5 m odpowiednio 6 i 12 na 40. Dlatego:
- uśredniaj punkt w Garminie (funkcja „uśrednianie punktu”, minuta przy każdym drzewie);
- wybieraj drzewa rozrzucone **6–14 m od środka**, w różnych kierunkach;
- wybieraj drzewa o **wyraźnie różnych pierśnicach** (po pierśnicy program rozpoznaje, które to drzewo);
- mierz pierśnicę taśmą na 1,3 m.

Ocena „niepewne” znaczy, że jest drugie, inaczej obrócone ustawienie prawie tak samo dobre. Wtedy sprawdź w QGIS warstwę `odchylki_gps`.

### Ścieżka skanera, teren i animacja przejazdu

**Ścieżka skanera** (trajektoria, którą przeszedłeś ze skanerem) nie jest potrzebna, ale gdy jest, wyniki mówią więcej.

- **Skąd ją bierze:** sam szuka pliku ze słowem `Trajectory`, `traj`, `sciezka`, `path`, `odom`, `pose` albo `track` w nazwie i z tym samym skrótem skanu, obok pliku skanu (i folder wyżej) albo w `wyniki\<skan>\01_RAPORT`. Dla `_N0h__r25.laz` znajdzie `_N0h_Trajectory.las`. Możesz też wybrać plik w oknie (wiersz **Ścieżka skanera** → **Wybierz…**, **Szukaj sam** wraca do szukania samemu) albo położyć go jako `01_RAPORT\<skan>_sciezka.<rozszerzenie>`.
- **Formaty:** `.las`, `.laz`, `.ply` (tekstowy i binarny) oraz tekstowe `.txt`, `.csv`, `.xyz`, `.pts`, `.asc`: eksporty GeoSLAM, Emesent, ROS (`field.pose.pose.position.x`), TUM, KITTI, zwykłe x y z. Separator (średnik, tabulator, przecinek, spacja), przecinek dziesiętny i kolumny rozpoznaje sam. Ścieżka musi być w tym samym układzie co skan, inaczej program ją pominie z uwagą w dzienniku.
- **Co daje:** w obrazkach drzew szary pierścień pokazuje strony pnia widziane ze ścieżki, a strzałka kierunek do ścieżki. W Excelu kolumny „Odległość od ścieżki skanera” i „Obejście ze ścieżki” (jaką część obwodu skaner obszedł bliżej niż 15 m) oraz w podsumowaniu długość ścieżki i liczba drzew dalej niż 12 m (te mają gorzej zmierzoną pierśnicę). W GeoPackage warstwa `sciezka_skanera`, w widoku 3D żółta linia.
- **Animacja przejazdu:** w widoku 3D grupa **Przejazd skanera**: ▶ odtwarza przejście, punkty pojawiają się, gdy skaner podejdzie bliżej niż 10 m. Suwak przewija, drugi suwak zmienia prędkość, **Kamera za skanerem** jedzie razem z nim, **Cała chmura** wraca do całości. Film zrobisz nagrywaniem ekranu (Win + Alt + R albo Win + G).

**Model terenu** liczy się sam z punktów gruntu (siatka 0,25 m) i trafia do `01_RAPORT\<skan>.gpkg` jako warstwy `teren_wysokosc` (wysokość), `teren_spadek` (spadek w stopniach), `teren_cieniowanie` (kolorowe cieniowanie) i `warstwice` (co 0,25 / 0,5 / 1 m zależnie od deniwelacji, co piąta pogrubiona: pole `glowna`). W Excelu w podsumowaniu jest najniższy punkt, deniwelacja, średni spadek (w stopniach i procentach), spadek najbardziej stromych miejsc i ekspozycja stoku. W widoku 3D przycisk **Teren** pokazuje półprzezroczystą powierzchnię gruntu. Wysokości są w układzie skanu; `_georef.gpkg` dostaje warstwice i ścieżkę, ale rastrów terenu nie (te zostają w zwykłym `.gpkg`).

Wszystkie wyniki jednego skanu lądują w **jednym folderze** `LidarTreeSegmenter\wyniki\<nazwa_skanu>\`, poukładane według rodzaju:

```
wyniki\<skan>\
  CZYTAJ_MNIE.txt        co gdzie leży
  01_RAPORT\             <skan>_RAPORT.xlsx, 00_PODSUMOWANIE.txt, <skan>_gatunki.csv
  02_CHMURY\             <skan>_segmenty.laz, <skan>_czesci.laz
  03_TABELE\             wszystkie tabele .csv i ustawienia .json
  04_OBRAZY_DRZEW\       drzewo_001.png, drzewo_002.png ...
  05_DZIENNIK\           zapis przebiegu z okna LidarTreeSegmenter
  06_WIDOK_3D\           <skan>_chmura_3d.html (chmura w 3D do przeglądarki)
```

| Plik | Co to jest |
|---|---|
| `01_RAPORT\<skan>_RAPORT.xlsx` | **raport Excel**: Podsumowanie (N/ha, D1,3, Dg, H, wysokość Loreya, G/ha, V/ha, rozkład pierśnic), Drzewa (jedno drzewo w wierszu, kolumny z jednostkami, filtr, suma), Ustawienia (opisane zdaniami), Objaśnienia |
| `01_RAPORT\00_PODSUMOWANIE.txt` | to samo podsumowanie i ustawienia jako zwykły tekst |
| `01_RAPORT\<skan>_gatunki.csv` | tu wpisujesz gatunek drzew (kolumna `gatunek_reczny`) |
| `01_RAPORT\<skan>_sprawdzenie.csv` | Twoje decyzje ze sprawdzania drzew (drzewo / krzak / złom, gatunek) |
| `01_RAPORT\<skan>_pomiar.csv` | pomiar terenowy kilku drzew (Garmin), patrz wyżej |
| `01_RAPORT\<skan>_georef.gpkg` | GeoPackage przesunięty do współrzędnych terenowych (gdy jest pomiar) |
| `01_RAPORT\<skan>.gpkg` | **GeoPackage** do QGIS: drzewa z gatunkiem, pierśnicą, wysokością i miąższością, przekroje i punkty na 1,3 m i 3 m, krzewy, teren |
| `01_RAPORT\<skan>.qgs` | **projekt QGIS**: dwuklik otwiera GeoPackage z gotowymi stylami |
| `06_WIDOK_3D\<skan>_chmura_3d.html` | chmura w 3D: otwórz dwuklikiem w przeglądarce, działa bez internetu |
| `06_WIDOK_3D\<skan>_sprawdzanie.html` | ten sam widok, od razu w trybie sprawdzania drzew |
| `03_TABELE\<skan>_ustawienia_lts.json` | wybrany drzewostan i gatunek dla skanu |
| `02_CHMURY\<skan>_segmenty.laz` | chmura z numerem drzewa przy każdym punkcie |
| `02_CHMURY\<skan>_czesci.laz` | chmura z polem `czesc`: pień / gałęzie / ulistnienie (CloudCompare: koloruj po `czesc`) |
| `03_TABELE\<skan>_drzewa.csv` | tabela drzew z kroku 1: pozycja, pierśnica, wysokość (numer drzewa = `id_drzewa`) |
| `03_TABELE\<skan>_czesci_drzewa.csv` | procent pnia, gałęzi i ulistnienia, zasięg pnia, pierśnica LidarTreeSegmenter, grupa gatunkowa |
| `03_TABELE\<skan>_pien_okregi.csv` | okręgi pnia co 20 cm aż do korony (kolumna `zrodlo`: pomiar albo rekonstrukcja) |
| `03_TABELE\<skan>_okregi.csv` | okręgi pnia z wykrywania drzew |
| `03_TABELE\<skan>_ustawienia.json` | ustawienia kroku 1 w postaci do odczytu przez program |
| `04_OBRAZY_DRZEW\drzewo_001.png ...` | obrazek **każdego** drzewa, po kolei, numer jak w tabeli |

Stare wyniki (pliki luzem i folder `podglad`) układają się same przy następnym uruchomieniu. Można też od razu: `python program\lts_uklad.py wyniki`.

**Gatunek.** Główne gatunki na mierzonych powierzchniach to świerk i buk. LidarTreeSegmenter rozpoznaje wstępnie grupę z kształtu drzewa: pień prowadzony do wierzchołka, ostry szczyt i stożkowa korona wskazują iglaste (czyli **świerk**), a rozwidlony pień i szeroka, zaokrąglona korona liściaste (czyli **buk**). Drzewa niższe niż 8 m i niejednoznaczne zostają „nieokreślone”. Gatunek jest w tytule obrazka drzewa, więc łatwo go sprawdzić. Błędny albo inny gatunek (np. jodła) wpisujesz w `<skan>_gatunki.csv` albo ustawiasz w sprawdzaniu drzew. To są reguły bez uczenia. Na S4v (same świerki) 15 drzew wyszło jako buki, bo w gęstym drzewostanie korony się zasłaniają. Gdy znasz gatunek całej powierzchni, wybierz w oknie „same świerki” albo „same buki” (albo `python program\30_raport.py wyniki\<skan> --gatunek świerk`).

**Gatunek z etykiet skanera.** Jeśli w terenie oznaczałeś drzewa skanerem (znacznik z kodem gatunku), program sam czyta `markPoint.csv` z surowego folderu sesji (np. `N0h_MT20260811-155717` obok folderu ze skanem) i przypisuje gatunek pniowi bliżej niż 1 m od etykiety. Kody: FI świerk, BU buk, TA jodła, KI sosna, LA modrzew, EI dąb, AH jawor, ES jesion, KR czereśnia, UL wiąz, taxus cis (oraz polskie SW, BK, JD, SO, MD, DB). Kolejność ważności: sprawdzanie drzew > `<skan>_gatunki.csv` > etykiety skanera > gatunek dla całej powierzchni > rozpoznanie z kształtu. Etykiety (także nieprzypisane) są w GeoPackage w warstwie `etykiety_skanera`. Własny plik etykiet możesz też położyć jako `01_RAPORT\<skan>_etykiety.csv`. Gatunek bez wzoru w `tablice_miazszosci.csv` liczy się wzorem swojej grupy (iglaste 0,45, liściaste 0,50).

**Obrazki drzew** mają trzy części: dwa widoki z boku (z lewej wysokość nad gruntem w metrach, na dole odległość od osi pnia, czerwona linia na 1,3 m) i przekrój na wysokości 1,3 m z góry z miarką w centymetrach, z którego da się odczytać pierśnicę. Dorysowany dół pnia jest **niebieski**.

**Drzewa zagubione w podszycie.** Wykrywanie drzew (tree_segmenter_tool) szuka pni w plastrach od 0,5 do 6 m. LidarTreeSegmenter puszcza je drugi raz wyżej, od 2,5 do 8,5 m, gdzie strzała jest zwykle czysta. Pień znaleziony tylko wyżej, który nie pokrywa się z żadnym znalezionym wcześniej, jest dodawany jako nowe drzewo. W Excelu ma „tak” w kolumnie „Wykryte od góry”, a jego pierśnica jest przedłużona w dół ze zbieżności pnia. Kod tree_segmenter_tool zostaje bez zmian, LidarTreeSegmenter tylko woła go dwa razy.

**Krzewy zamiast drzew (kontrola pnia).** Pień w przekroju jest pusty w środku: punkty leżą tylko na korze, po jednej stronie albo dookoła. Krzew albo kępa gałęzi ma punkty także w środku okręgu. LidarTreeSegmenter sprawdza to na wysokości 1,3 m i drugi raz na 3 m. Liczy, jaka część punktów przy okręgu leży bliżej środka niż 0,7 promienia. Test działa także wtedy, gdy skaner widział tylko kawałek obwodu, a samo słabe pokrycie nie odrzuca drzewa. Obiekt pełny w środku i niższy niż 10 m jest oznaczany jako **krzew**. W Excelu jest na szaro pod tabelą i nie wchodzi do sum ani do wartości na hektar. Wysokie drzewo z punktami w środku dostaje uwagę „niepewny” i zostaje w wynikach. Pierśnica z mniej niż 40 punktów jest oznaczona jako niepewna. Granica wysokości zależy od klasy drzewostanu (`wysokosc_krzewu_m` w `klasy_drzewostanu.csv`: 5 m dla młodego, 10 m dla dojrzałego).

**Za gruby jak na wysokość: złom albo krzew.** Drzewo niskie i bardzo grube (np. 5,8 m wysokości przy 83 cm pierśnicy, smukłość poniżej 20) nie istnieje jako zdrowe drzewo. Jeśli pień jest wyraźnie pusty w środku na 1,3 m i na 3 m, to **złom** (złamane drzewo): zostaje w wynikach, a jego miąższość to objętość zmierzonej strzały, nie wzór z wysokością. Jeśli pusty nie jest, to pniak albo kępa krzewów i wypada z wyników jako **krzew**. Powód jest w kolumnie uwag. Na S4v: złomy 3 i 22, krzewy m.in. 15, 30 i 63.

**Podszyt.** Krzewy przy pniu łapały się wcześniej jako gałęzie. Teraz punkty gałęzi i liści nisko przy ziemi (do 1,5 m w młodym, do 3 m w dojrzałym drzewostanie) i dalej od pnia niż 0,6 / 1 m są osobną klasą **podszyt** (szaroniebieski na obrazkach i w widoku 3D, klasa 5 w `_czesci.laz`).

**Pierśnica, gdy dwie metody się nie zgadzają.** Krok 1 i LidarTreeSegmenter mierzą pierśnicę osobno. Gdy różnią się o ponad 30%, raport bierze tę, która lepiej pasuje do krzywej wysokości drzewostanu (wysokość od pierśnicy, dopasowana na drzewach, gdzie obie metody się zgadzają). Taki wybór ma uwagę w Excelu. Na S4v drzewo 33 (13,8 m) dostało 17,6 cm zamiast 7,2 cm, a drzewo 26 (9 m) zostało przy 14,6 cm. Obrazek drzewa pokazuje wtedy obie wartości. Drzewo, którego pierśnica w ogóle nie pasuje do wysokości, dostaje uwagę „sprawdź na obrazku”.

**Gęsty podszyt.** Gdy dół pnia jest zasłonięty krzewami, LidarTreeSegmenter szuka pnia także od góry (od 2 do 6,5 m, gdzie strzała jest zwykle czysta), schodzi nim w dół i sprawdza zbieżność. Jeśli niżej zamiast pnia jest gruba kępa, ten odcinek jest **dorysowany** z przedłużenia strzały. W Excelu taka pierśnica ma niebieskie tło i źródło „rekonstrukcja”.

**Miąższość** w raporcie to miąższość grubizny, liczona wzorem dla gatunku drzewa z pliku `tablice_miazszosci.csv`. Na razie są tam wzory ogólne V = g·h·f (g to pole przekroju w pierśnicy, h wysokość, f pierśnicowa liczba kształtu): świerk 0,47, buk 0,51, nieokreślony 0,47, a gatunki bez własnego wiersza wzorem grupy: iglaste 0,45, liściaste 0,50 (przybliżone). Plik otworzysz w Excelu albo Notatniku i możesz go podmienić na tablice regionalne (także wzory potęgowe V = a·d^b·h^c, opis jest w pliku).

Gatunek każdego drzewa wpisujesz w `wyniki\<skan>\01_RAPORT\<skan>_gatunki.csv` (kolumna `gatunek_reczny`, np. `świerk`, `buk`, `jodła`; gatunek spoza tablic liczy się wzorem „nieokreślony”). Plik powstaje sam przy pierwszym raporcie. Po wpisaniu uruchom sam raport jeszcze raz (sekunda):

```
python program\30_raport.py wyniki\<skan>
```

Drzewa bez rozpoznanego ani wpisanego gatunku liczone są jako „nieokreślony”. Inny domyślny gatunek podasz tak: `python program\30_raport.py wyniki\<skan> --grupa świerk`.

**GeoPackage (`01_RAPORT\<skan>.gpkg`).** Jeden plik z warstwami do QGIS (przeciągnij go do okna QGIS): `drzewa` (punkt pnia ze wszystkimi danymi z raportu, w tym gatunkiem, skąd jest gatunek i pewnością rozpoznania), `przekroj_1_3m` i `przekroj_3m` (okręgi pnia ze średnicą, pokryciem obwodu i wynikiem kontroli pnia), `punkty_1_3m` i `punkty_3m` (punkty chmury w plastrze ±5 cm, jednym kolorem; część drzewa jest w polu `czesc`). Do tego teren (`teren_wysokosc`, `teren_spadek`, `teren_cieniowanie`, `warstwice`), `krzewy` (obrysy krzewów z polem i wysokością) i, jeśli jest, `sciezka_skanera`. Osi pni, gałęzi i koron już nie ma (było za dużo warstw); "Przelicz raport" usuwa je też ze starych plików. Współrzędne są takie jak w skanie. Skan bez układu współrzędnych dostaje układ lokalny w metrach ("LidarTreeSegmenter - lokalny uklad skanu"), więc skala w QGIS jest prawdziwa.

**Projekt QGIS (`01_RAPORT\<skan>.qgs`).** Kliknij go dwa razy: QGIS otworzy wszystkie warstwy w dobrej kolejności i z kolorami (teren na spodzie, warstwice, przezroczyste korony, ścieżka, drzewa w kolorach gatunków z numerami). Style są też zapisane w samym `.gpkg`, więc po przeciągnięciu pliku wyglądają tak samo. Punkty plastrów są przerzedzone (kora co 1 cm, reszta co 4 cm), ukryte na starcie i rysują się od skali 1:400; pole `odl_od_okregu_cm` to odległość punktu od okręgu pnia. Gdy jest pomiar terenowy, powstaje też `<skan>_georef.qgs`. Starsze wyniki poprawia **Przelicz raport**.

**Widok 3D (`06_WIDOK_3D\<skan>_chmura_3d.html`).** Otwórz dwuklikiem w Chrome, Edge albo Firefoksie. Lewy przycisk myszy obraca, prawy przesuwa, kółko przybliża. Kolor wg drzewa, części (pień / gałęzie / ulistnienie) albo wysokości. Kliknięcie w drzewo pokazuje numer, gatunek, pierśnicę, wysokość i miąższość, a „Tylko to drzewo” zostawia je samo. Chmura jest przerzedzona do 600 tys. punktów, żeby plik był lekki (gęstszą zrobisz tak: `python program\40_widok_3d.py wyniki\<skan> --punktow 1500000`).

Dodatkowo kolumna „Miąższość zmierzonej strzały” podaje objętość odcinka pnia, który skaner faktycznie widział (bez wierzchołka). Jest kontrolą, a nie miąższością drzewa.

Drzewa, które zna tylko LidarTreeSegmenter (krok 1 nie zmierzył ich na 1,3 m), też trafiają do raportu, żeby złomy i krzewy nie znikały po cichu.

Jeśli skan był już raz liczony, krok 1 jest pomijany. Wynik z `tree_segmenter_tool\results` zostaje wtedy przeniesiony tutaj.

Skan jest liczony w całości, bez przycinania do koła. Duży skan (40 mln punktów i więcej) potrzebuje około 8 GB wolnej pamięci. Jeśli program się wyłączy, przytnij skan w CloudCompare.

## Co tu jest

```
LidarTreeSegmenter\
  LidarTreeSegmenter_PL.bat     okno programu (start tutaj)
  PRZECIAGNIJ_TU_SKAN.bat       to samo bez okna (upuść skan na plik)
  ZAINSTALUJ_RAZ.bat            instalacja bibliotek
  README.md                     opis po angielsku (docs\CZYTAJ_MNIE_PL.md - ten opis)
  tablice_miazszosci.csv        wzory miąższości (można podmienić)
  klasy_drzewostanu.csv         ustawienia dla drzewostanu młodego i dojrzałego
  SZABLON_pomiar.csv            wzór pliku pomiaru terenowego (Garmin)
  wyniki\<skan>\                wyniki skanów (01_RAPORT, 02_CHMURY ...)
  wyniki\KOLEJKA_<data>.xlsx     zestawienie powierzchni z kolejki na noc
  porownanie\<pow>\             rankingi metod segmentacji
  metody\<metoda>\<pow>.laz     wyniki metod we wspólnym formacie
  program\                      kod, nie trzeba tu zaglądać:
    LidarTreeSegmenter_okno.py    okno
    05_wykryj_drzewa.py         wykrywanie drzew: tree_segmenter_tool + szukanie pni od góry
    10_pien_galezie_liscie.py   pień, gałęzie, ulistnienie, grupa gatunkowa, obrazki
    30_raport.py                raport Excel, miąższość, 00_PODSUMOWANIE.txt
    40_widok_3d.py              chmura w 3D jako plik HTML
    lts_gpkg.py               zapis GeoPackage (bez dodatkowych bibliotek)
    lts_qgis.py               style warstw i projekt QGIS (.qgs)
    lts_krzewy.py             krzewy 0,3-4 m jako osobne obiekty (krok 3)
    lts_teren.py              dopasowanie skanu do drzew zmierzonych w terenie
    lts_sciezka.py            ścieżka skanera: szukanie, odczyt formatów, widoczność drzew
    lts_dtm.py                model terenu: siatka, spadek, warstwice, rastry do GeoPackage
    lts_etykiety.py           gatunek z etykiet zapisanych skanerem (markPoint.csv)
    lts_ustawienia.py         klasa drzewostanu i gatunek skanu
    lts_na_zywo.py            podgląd chmury na żywo w oknie
    biblioteki_js\              three.js do widoku 3D (licencja MIT)
    lts_uklad.py              porządek w folderze wyników
    20_porownaj_segmentacje.py  ranking metod segmentacji względem wzorców
    21_ujednolic_wynik.py       wynik dowolnego narzędzia do wspólnego formatu
  tree_segmenter_tool\          02_detect_trees.py - wykrywanie pni i segmentacja (krok 1)
```

Biblioteki są te same co w `tree_segmenter_tool`, plus `openpyxl` do Excela:

```
python -m pip install laspy lazrs numpy pandas scipy scikit-learn matplotlib openpyxl
```

Wszystkie komendy wpisujesz w konsoli otwartej w folderze programu (tam, gdzie leży `LidarTreeSegmenter_PL.bat`).

---

## 1. Pień, gałęzie, ulistnienie

```
python program\10_pien_galezie_liscie.py ..\tree_segmenter_tool\results\<skan>\<skan>_segmenty.laz
```

Działa na każdej chmurze, w której punkty mają numer drzewa (`treeID_pred` z tree_segmenter_tool albo `treeID` z Twoich wzorców).

**Jak to działa:**

1. Pień jest śledzony od 1 m w górę i w dół plastrami co 20 cm. W każdym plastrze szukany jest okrąg tam, gdzie pień powinien być. Idzie to do korony, także przy pniach wygiętych.
2. Każdy punkt dostaje cechy kształtu: czy leży na linii (gałąź), czy w rozproszonej kępie (liście).
3. Model uczy się sam na tej chmurze. Pewne drewno to pień i wyraźne gałęzie, pewne liście to rozproszone kępy z dala od pnia. Las losowy rozstrzyga resztę.
4. Na końcu małe, samotne kawałki „drewna” w koronie trafiają do ulistnienia.

**Wynik** w `wyniki\<skan>\` (chmury w `02_CHMURY`, tabele w `03_TABELE`):

- `<skan>_czesci.laz` ma pole `czesc` (1 pień, 2 gałęzie, 3 ulistnienie, 0 nic) i `p_drewno` (0..1). Klasyfikacja LAS jest ustawiona tak, że CloudCompare koloruje od razu.
- `<skan>_czesci_drzewa.csv` podaje dla każdego drzewa, do jakiej wysokości sięga pień, średnicę na 1,3 m i u góry oraz procent punktów w każdej części.
- `<skan>_pien_okregi.csv` to okręgi pnia co 20 cm, czyli gotowa krzywa zbieżystości.
- `04_OBRAZY_DRZEW\` zawiera obrazek każdego drzewa, po kolei według numeru.

W `wyniki\` są już tabele i obrazki z moich przebiegów na obu wzorcach. Pliku `_czesci.laz` nie kopiowałem, bo jest za duży. Żeby go mieć, uruchom:

```
python program\10_pien_galezie_liscie.py ..\DANE\tree_conected\So2_testy.laz
```

**Co sprawdziłem** na Twoich wzorcach (So2: 1,4 min, 9F: 5 min):

- Pień został znaleziony w 35 z 36 drzew na So2 i w 105 ze 113 na 9F. Na obrazkach idzie równo z pniem aż do korony.
- Średnica na 1,3 m zgadza się z tree_segmenter_tool z medianą różnicy 1,9 cm (52 drzewa na 9F). Około 6 drzew różni się o ponad 15 cm. Jeszcze nie wiadomo, która metoda się tam myli.
- Podziału gałęzie / ulistnienie **nie da się jeszcze zmierzyć liczbowo**, bo nie ma chmury z ręcznie oznaczonym drewnem i liśćmi. Pole `pwood` w 9F się do tego nie nadaje: 97% punktów ma tam wartość powyżej 0,5. Oceniałem to tylko na obrazkach.
- 9F to chyba skan bezlistny (grudzień). Wtedy „ulistnienie” oznacza w praktyce drobne gałązki.

**Żeby to zmierzyć porządnie:** oznacz w CloudCompare 3 do 5 drzew na drewno i liście (narzędzie Segment), zapisz je, a dopiszę porównanie.

---

## 2. Porównywanie segmentacji

Każda metoda trafia do wspólnego formatu, a potem jeden skrypt ocenia wszystkie naraz.

**Krok 1. Ujednolić wynik metody**

```
python program\21_ujednolic_wynik.py <plik albo folder> --metoda <nazwa> --powierzchnia 9F
```

Skrypt sam szuka pola z numerem drzewa (`treeID_pred`, `final_segs`, `tree_ID`, `PredInstance`, `instance_pred` i inne). Folder z plikiem na każde drzewo (np. eksport Segfix) też przyjmie. Gdy nie zgadnie, wypisze pola i podasz właściwe przez `--pole`.

**Krok 2. Porównać**

```
python program\20_porownaj_segmentacje.py 9F
python program\20_porownaj_segmentacje.py So2
```

Najważniejsza kolumna to **F1** (im wyżej, tym lepiej). Opis pozostałych jest na początku skryptu. Trafienie to para drzew, które pokrywają się w co najmniej połowie (IoU ≥ 0,5). Próg zmienisz przez `--min-iou 0.3`.

**Ważne:** metodę trzeba puścić na tym samym skanie, z którego zrobiony jest wzorzec, w tym samym układzie współrzędnych. Dla 9F to `DANE\Bulgaria\9F_segmented_segfix_2.laz`, a dla So2 `DANE\_3DFin_\_S2o__r20.las`.

**Nowy wzorzec** robisz skryptem `94_merge_segments.py` i dopisujesz go w `WZORCE` na górze `20_porownaj_segmentacje.py`.

### Co już jest w `metody\`

Liczby niżej są z mojego przebiegu na tych samych plikach.

| Metoda | Skąd | Powierzchnia |
|---|---|---|
| `tree_segmenter_tool` | `tree_segmenter_tool\results\9F_segmented_segfix_2_r30\...segmenty.laz` | 9F |
| `tree_segmenter_tool` | `DANE\_3DFin_\_S2o__r20_segmenty.laz` | So2 |
| `3DFin` | `DANE\_3DFin_\_S2o__r20.las` (pole `tree_ID`) | So2 |
| `auto_przed_poprawkami` | `DANE\Bulgaria\9F_segmented.laz`, czyli automatyczna segmentacja przed Twoimi poprawkami | 9F |

Plik `DANE\TreeISO\S2o_r20.las` **nie zawiera wyniku TreeISO**: nie ma w nim żadnego pola z numerem segmentu, tylko prawdziwe kolory i intensywność. Trzeba zapisać go jeszcze raz z CloudCompare (punkt 3b).

### Wyniki So2 (36 drzew)

| Metoda | F1 | Czułość | Precyzja | Śr. IoU |
|---|---|---|---|---|
| tree_segmenter_tool | 76,7 | 63,9% | 95,8% | 0,81 |
| 3DFin | 63,0 | 47,2% | 94,4% | 0,79 |

Obie metody rzadko wymyślają drzewa (precyzja około 95%), ale gubią sporo prawdziwych. Większość „przeoczonych” ma IoU 0,3 do 0,45. Takie drzewo zostało znalezione, tylko korona jest wymieszana z sąsiadem. Metody mylą się też na **różnych** drzewach, więc warto je kiedyś połączyć.

### Wyniki 9F (113 drzew, razem z podrostem)

| Metoda | F1 | Czułość | Precyzja | Śr. IoU | Czułość: drzewa ≥ 10 m | Czułość: niższe |
|---|---|---|---|---|---|---|
| auto_przed_poprawkami | 73,5 | 82,3% | 66,4% | 0,84 | 88% | 55% |
| tree_segmenter_tool | 61,5 | 53,1% | 73,2% | 0,69 | 62% | 10% |

Wynik `auto_przed_poprawkami` jest zawyżony, bo Twój wzorzec powstał przez poprawianie właśnie tej segmentacji. Traktuj go jako górną granicę, a nie jako konkurenta.

Czułość tree_segmenter_tool wychodzi tu niższa niż 91% z jego README. Przyczyna leży w sposobie liczenia, a nie w błędzie. README sprawdzał, czy znaleziono **pień** grubego drzewa. Tutaj liczy się też **korona** (IoU ≥ 0,5) i liczą się wszystkie 113 drzew. Z 84 drzew wyższych niż 15 m tree_segmenter znajduje 83% przy IoU ≥ 0,3, ale tylko 63% przy 0,5. Pnie więc znajduje, a gubi się w rozdzielaniu koron i prawie nie wykrywa podrostu (10%). Przy `--min-iou 0.3` ma F1 74,9 i precyzję 89%.

---

## 3. Od jakich metod zacząć

Masz kartę Intel, a nie NVIDIA, więc na początek same metody działające na CPU:

**a) tree_segmenter_tool** jest punktem odniesienia i już go masz.

**b) 3DFin** też już używałeś. Na So2 znalazł 21 z 36 drzew. Warto puścić go jeszcze raz ze zmienionymi ustawieniami plastra, w którym szuka pni, i porównać obie wersje jako `3DFin_v2`.

**c) TreeISO w CloudCompare** (wtyczka TreeIso, w CloudCompare 2.13 i nowszym, menu Plugins). Nie trzeba nic programować:

1. Otwórz skan, uruchom TreeIso z domyślnymi ustawieniami.
2. Pojawi się pole skalarne `final_segs`.
3. Zapisz chmurę jako LAS, zaznaczając zapis pól skalarnych.
4. `python program\21_ujednolic_wynik.py <zapisany.las> --metoda TreeISO --powierzchnia So2`

**Później, z kartą NVIDIA albo maszyną w chmurze:** SegmentAnyTree (gotowy obraz Docker) i ForestFormer3D. To modele uczone, zwykle lepsze w gęstych koronach. Do porównania wchodzą tak samo, przez `21_ujednolic_wynik.py`.

## 4. Łączenie wyników (następny krok)

Gdy będą 3 metody z wynikami, da się zrobić `22_polacz_segmentacje.py`. Pnie można brać z metody o najlepszej czułości, a korony rozdzielać tą, która ma najwyższe IoU, albo głosować punkt po punkcie. Ranking z punktu 2 pokaże, czy to się opłaca.

## Krzewy i zrośnięte drzewa

**Krzewy.** Raport (krok 3) szuka krzewów jako osobnych obiektów: brył gałęzi i liści 0,3–4 m nad gruntem poza pniami (siatka 25 cm, co najmniej 3 zajęte warstwy po 25 cm między 0,5 a 3,25 m, co najmniej 0,5 m²). Pień i 15 cm wokół kory nigdy nie są krzewem, więc pierśnica się nie zmienia. Wynik: arkusz **Krzewy** w Excelu, wiersze o krzewach w podsumowaniu, warstwa `krzewy` w GeoPackage, fioletowe punkty w widoku 3D, plik `03_TABELE\<skan>_krzewy.csv`. Stare wyniki poprawia **Przelicz raport**.

**Dwa drzewa w jednym.** Krok 2 szuka w każdym drzewie drugiego, osobnego pnia (co najmniej 4 m, 10 cm, do 20° od pionu, obok pnia głównego). Gdy drugi pień widać osobno na 1,3 m albo stoi wyraźnie dalej, powstaje nowe drzewo; rozwidlenie powyżej 1,3 m zostaje jednym drzewem z uwagą. Lista: `03_TABELE\<skan>_rozdzielone.csv`. Na starszym skanie kliknij **Start** (etap 1 zostaje, etap 2 liczy się od nowa). Wyłączenie: `--bez-rozdzielania`.

