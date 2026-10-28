"""
PIPELINE INWENTARYZACJI LASU Z CHMURY PUNKTOW TLS
=================================================

Co ten skrypt robi, po kolei:

  KROK 1  Wczytanie pliku .laz
  KROK 2  Usuniecie szumu (samotne punkty wiszace w powietrzu)
  KROK 3  Znalezienie gruntu i zbudowanie modelu terenu (DTM)
  KROK 4  Normalizacja wysokosci (kazdy punkt dostaje wysokosc NAD GRUNTEM)
  KROK 5  Wykrycie pni drzew
  KROK 6  Przypisanie wszystkich punktow do drzew (segmentacja)
  KROK 7  Pomiar piersnicy DBH (dopasowanie okregu na 1.3 m)
  KROK 8  Pomiar wysokosci drzew
  KROK 9  Zapis: tabela CSV + chmura .laz z numerami drzew

ZERO uczenia maszynowego. Wszystko to geometria - liczenie odleglosci,
grupowanie sasiadow i dopasowywanie okregow. Dziala od razu, bez danych
treningowych i bez karty graficznej.

URUCHOMIENIE:
    python pipeline_las.py dane/las_testowy.laz
    python pipeline_las.py dane/las_testowy.laz --wyniki moje_wyniki

Wymagane biblioteki:
    pip install "laspy[lazrs]" numpy scipy scikit-learn pandas
"""

import argparse
import sys
from pathlib import Path

import laspy
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree
from scipy.interpolate import griddata
from sklearn.cluster import DBSCAN


# ======================================================================
# PARAMETRY
# ======================================================================
# To jest jedyne miejsce, ktore bedziesz podkrecal pod swoje dane.
# Kazdy parametr ma komentarz: co robi i co sie stanie, gdy go zmienisz.

class Parametry:

    # --- KROK 2: filtr szumu ---------------------------------------
    SOR_SASIEDZI = 12
    # Ilu najblizszych sasiadow sprawdzamy dla kazdego punktu.
    # Mniej = szybciej ale mniej pewnie. 10-20 to rozsadny zakres.

    SOR_PROG_ODCHYLEN = 2.5
    # Ile odchylen standardowych od sredniej wolno punktowi odstawac.
    # MNIEJSZA wartosc = agresywniejsze czyszczenie (ryzyko: zjada cienkie
    # galazki i czubki drzew!). WIEKSZA = zostawia wiecej szumu.
    # Jesli po filtracji znikaja Ci czubki drzew - podnies do 3.0-3.5.

    # --- KROK 3: grunt ----------------------------------------------
    DTM_ROZMIAR_KOMORKI = 0.5
    # Bok kwadratowej komorki siatki w metrach. W kazdej komorce szukamy
    # najnizszego punktu i uznajemy go za grunt.
    # ZA MALA (np. 0.1 m): w komorce moze nie byc zadnego punktu gruntu,
    #   bo przeslania ja pien - grunt bedzie dziurawy.
    # ZA DUZA (np. 3 m): na zboczu zgubisz nachylenie, wysokosci wyjda zle.
    # 0.5 m dziala dobrze dla TLS. Dla gestego podszytu probuj 1.0 m.

    DTM_MAX_SKOK_MIEDZY_KOMORKAMI = 0.40
    # ZABEZPIECZENIE NR 1 - najwazniejsze w calym DTM. Maksymalna dozwolona
    # roznica wysokosci gruntu miedzy dwiema SASIADUJACYMI komorkami.
    #
    # PROBLEM, ktory rozwiazuje (widoczny na kazdym skanie z jednego
    # stanowiska): skaner widzi ziemie tylko wokol siebie. Dalej patrzy coraz
    # plaszczej, az w koncu widzi juz tylko korony - ziemie zaslania mu
    # wszystko, co po drodze. W tych dalekich komorkach "najnizszy punkt"
    # to galaz 20 m nad gruntem, i DTM skacze tam o 20 m.
    #
    # ROZWIAZANIE - rozrost od srodka (region growing):
    #   1. Znajdz komorke o najnizszym punkcie w calym skanie. To na pewno grunt.
    #   2. Rozlewaj sie na sasiadow, ale przechodz do sasiada TYLKO jesli
    #      roznica wysokosci jest mniejsza niz ten parametr.
    #   3. Czego nie dalo sie osiagnac - tam gruntu nie zaobserwowano.
    #
    # Dziala, bo prawdziwy teren zmienia sie plynnie, a przejscie z gruntu
    # na korone to skok o kilkanascie metrow - rozrost sie tam zatrzymuje.
    # Nie przeszkadza mu, ze obszar bez gruntu jest szeroki (filtr oknowy
    # na tym wlasnie polegl).
    #
    # DOBOR: przy komorce 0.5 m wartosc 0.40 m dopuszcza nachylenie do 80%.
    # To duzo. Jesli masz urwiska albo skarpy - podnies. Jesli DTM "wycieka"
    # po pniach do gory - zmniejsz do 0.25.

    DTM_MAX_ODLEGLOSC_EKSTRAPOLACJI = 4.0
    # Jak daleko (w metrach) od najblizszej komorki Z ZAOBSERWOWANYM gruntem
    # wolno jeszcze ufac wysokosciom.
    #
    # Poza tym zasiegiem grunt jest zgadywany, wiec wysokosci drzew tam sa
    # niepewne. Pipeline NIE wyrzuca tych drzew - oznacza je w kolumnie
    # `uwagi_grunt` w tabeli wynikowej, zebys wiedzial, ktorym nie ufac.
    # Pierśnica pozostaje wiarygodna duzo dalej niz wysokosc, bo zalezy od
    # gruntu tylko przez to, gdzie wypadnie plaster 1.3 m.

    DTM_MAX_ROZNICA_SASIADA = 0.5
    # ZABEZPIECZENIE NR 2 - drobniejsze. Jesli "grunt" w komorce jest wyzszy
    # od medianowego gruntu najblizszych sasiadow o wiecej niz tyle metrow,
    # odrzucamy go. Lapie lezace klody, kopce i gesty mech, ktore pierwszy
    # filtr przepuscil.

    # --- KROK 0: wstepne przerzedzenie -------------------------------
    VOXEL_WEJSCIOWY = 0.01
    # Skan TLS potrafi miec 5000 punktow na metr kwadratowy - duzo wiecej,
    # niz potrzeba do pomiaru pierśnicy i wysokosci. Przerzedzamy go na wejsciu:
    # dzielimy przestrzen na szescianiki o tym boku i z kazdego zostawiamy
    # jeden punkt.
    # 0.01 m (1 cm) jest BEZPIECZNE - pien o srednicy 30 cm nadal dostaje
    # ~90 punktow na obwodzie, czyli az nadto do dopasowania okregu.
    # Ustaw 0, zeby wylaczyc przerzedzanie.
    # Na danych testowych (450 tys. pkt) nie robi roznicy. Na prawdziwym
    # skanie (5 mln pkt) skraca caly przebieg kilkukrotnie.

    # --- KROK 5: detekcja pni ---------------------------------------
    UZYJ_FILTRU_PIONOWOSCI = True
    # WLACZ TO W GESTYM LESIE. Rozwiazuje najczestszy problem prawdziwych
    # skanow TLS: na wysokosci 1-2 m nie ma samych pni, tylko pnie PLUS
    # mnostwo galezi, krzakow i igliwia. Zwykly DBSCAN grupuje to wszystko
    # razem i zamiast kilkudziesieciu kolek dostajesz wielkie kleksy.
    #
    # POMYSL: pien to powierzchnia PIONOWA. Galaz, lisc czy ziemia - nie.
    # Dla kazdego punktu liczymy, jak ustawiona jest powierzchnia, na ktorej
    # lezy (jej wektor normalny). Dla scianki pnia normalna jest POZIOMA.
    # Zostawiamy tylko takie punkty - i nagle zostaja same pnie.
    #
    # Jesli masz czysty, przerzedzony drzewostan bez galezi nisko, mozesz
    # to wylaczyc (False) - bedzie szybciej.

    PIONOWOSC_PROMIEN_SASIEDZTWA = 20
    # Ilu sasiadow bierzemy do wyznaczenia powierzchni wokol punktu.

    PIONOWOSC_MAX_NZ = 0.25
    # Ile pionowej skladowej wolno miec wektorowi normalnemu.
    # 0 = powierzchnia idealnie pionowa (sciana pnia).
    # 1 = powierzchnia pozioma (ziemia, gorna strona galezi).
    # MNIEJSZA wartosc = ostrzejszy filtr, zostaje mniej, same najpewniejsze
    # pnie. WIEKSZA = przepuszcza pochylone galezie.

    CIAGLOSC_KOMORKA_XY = 0.10
    CIAGLOSC_KROK_PIONOWY = 0.25
    CIAGLOSC_MIN_POZIOMOW = 8
    # DRUGI FILTR: ciaglosc w pionie. Nawet po filtrze pionowosci zostaja
    # kawalki pionowo stojacych galezi. Ale pien ma te wlasnosc, ze ciagnie
    # sie W GORE przez cala wysokosc plastra, a galaz nie.
    #
    # Liczymy to tak: dzielimy teren na slupki o podstawie CIAGLOSC_KOMORKA_XY
    # i kroimy plaster na poziomy co CIAGLOSC_KROK_PIONOWY. Slupek jest
    # kandydatem na pien, jesli ma punkty w co najmniej CIAGLOSC_MIN_POZIOMOW
    # poziomach.
    # Przy ustawieniach domyslnych (plaster 1-4 m, krok 0.25 m = 12 poziomow,
    # wymagane 8) oznacza to "cos stoi tu pionowo przez co najmniej 2 m".

    # --- KROK 5: SLEDZENIE PNI PRZEZ PLASTRY -------------------------
    # To jest glowna metoda wykrywania drzew. Pomysl w jednym zdaniu:
    #
    #   PIEN TO LANCUCH OKREGOW LEZACYCH JEDEN NAD DRUGIM.
    #
    # Zamiast szukac pni w jednym plastrze (co myli sie na krzakach), kroimy
    # dolne 6 metrow lasu na cienkie plastry, w KAZDYM szukamy okregow,
    # a potem laczymy je w pionowe lancuchy.
    #
    #   - prawdziwy pien: okregi o podobnym promieniu, jeden nad drugim,
    #     przez wiele metrow -> dlugi lancuch
    #   - krzak albo kepa galezi: w jednym plastrze cos okraglego sie trafi,
    #     ale pietro wyzej jest gdzie indziej i ma inny promien -> lancuch
    #     sie nie tworzy albo jest bardzo krotki -> odrzucamy
    #
    # To jest geometryczne rozroznienie drzewa od krzaka i NIE wymaga zadnych
    # danych treningowych.

    SLEDZENIE_DOL = 0.5
    SLEDZENIE_GORA = 6.0
    SLEDZENIE_KROK = 0.25
    # Zakres wysokosci nad gruntem i grubosc plastra. Przy tych wartosciach
    # powstaje 22 plastry. Nie zaczynam od 0, bo tam sa nabiegi korzeniowe
    # i runo. Nie ide wyzej niz 6 m, bo wyzej zaczynaja sie korony.

    SLEDZENIE_MAX_PRZESUNIECIE = 0.25
    # O ile metrow srodek okregu moze przesunac sie miedzy sasiednimi
    # plastrami, zeby nadal uznac, ze to ten sam pien.
    # Pien rosnie prawie pionowo, wiec na 25 cm wysokosci przesuwa sie
    # o par centymetrow. 0.15 m daje zapas na pnie pochylone.
    # ZA DUZA: lancuch "przeskoczy" na sasiednie drzewo.

    SLEDZENIE_MAX_ZMIANA_PROMIENIA = 0.5
    # O ile WZGLEDNIE moze zmienic sie promien miedzy plastrami (0.5 = 50%).
    # Pien zweza sie powoli, wiec realna zmiana to ulamek procenta. Luzny
    # prog jest tu celowy - chodzi tylko o odrzucenie ewidentnych bzdur.

    SLEDZENIE_MAX_PRZERWA = 3
    # Ile kolejnych plastrow lancuch moze "przeskoczyc", gdy pien jest
    # chwilowo zaslonity (galaz przed nim, cien skanowania). Bez tego kazde
    # zaslonienie rozbijaloby pien na dwa krotkie lancuchy.

    SLEDZENIE_MIN_PLASTROW = 6
    SLEDZENIE_MIN_ODLEGLOSC_DRZEW = 0.5
    # Dwa lancuchy, ktorych osie na 1.3 m sa blizej siebie niz tyle metrow,
    # scalamy w jedno drzewo (zostaje dluzszy). Bez tego jeden pien potrafi
    # dac 2-3 osobne lancuchy, gdy zaslonienie rozbije go na kawalki -
    # i w tabeli pojawia sie trzy drzewa zamiast jednego.
    # Ile plastrow musi miec lancuch, zeby uznac go za drzewo.
    # 8 plastrow po 0.25 m = 2 metry pnia. TO JEST GLOWNY PARAMETR
    # ODDZIELAJACY DRZEWA OD KRZAKOW. Podnies, jesli krzaki nadal przechodza.

    SLEDZENIE_VOXEL = 0.03
    # Przerzedzenie POJEDYNCZEGO plastra przed grupowaniem.
    #
    # Musi byc DROBNIEJSZE niz DBSCAN_VOXEL, i to jest wazne: przerzedzenie
    # do 5 cm wprowadza do polozenia punktu blad do 2.5 cm, a wtedy sredni
    # blad dopasowania okregu rosnie do ~4 cm - czyli dokladnie do progu
    # DBH_MAX_BLAD_DOPASOWANIA, i prawdziwe pnie zaczynaja byc odrzucane.
    # Przy 3 cm blad wraca do 1-2 cm i wykrywalnosc podwaja sie.
    # Ponizej 3 cm nic sie juz nie poprawia, a liczy sie dluzej.

    SLEDZENIE_DBSCAN_EPS = 0.15
    SLEDZENIE_DBSCAN_MIN = 10
    # Grupowanie wewnatrz pojedynczego plastra. Promien jest maly, bo w
    # jednym cienkim plastrze przekroj pnia to zwarty pierscien, a zalezy
    # nam, zeby nie skleic go z galezia obok.

    MAX_PROMIEN_ANALIZY = 0.0
    # Ogranicza analize do kola o tym promieniu wokol srodka skanu
    # (0 = bez ograniczenia).
    # PO CO: w skanie z jednego stanowiska dane sa dobre tylko do pewnej
    # odleglosci. Dalej punktow jest malo, pnie sa widziane z jednej strony
    # pod ostrym katem i wyniki sa zgadywaniem. Lepiej je uczciwie wyciac,
    # niz wpisywac do tabeli.
    # Srodek skanu wyznaczam automatycznie jako najgestsze miejsce chmury.

    WARSTWA_PNI_DOL = 1.0
    WARSTWA_PNI_GORA = 4.0
    # Z jakiego przedzialu wysokosci NAD GRUNTEM wycinamy poziomy "plaster",
    # w ktorym szukamy pni. Na tej wysokosci sa juz tylko pnie - nie ma
    # runa ani nabiegow korzeniowych, a korony sa wyzej.
    # Jesli masz gesty podszyt do 2 m, podnies oba (np. 2.0-3.0) - ale wtedy
    # DBH policzysz ekstrapolujac, bo 1.3 m wypadnie ponizej plastra.

    DBSCAN_VOXEL = 0.05
    # Przerzedzenie kandydatow na pnie TUZ PRZED grupowaniem.
    #
    # DLACZEGO TO JEST KONIECZNE, a nie "mile widziane":
    #   DBSCAN musi dla kazdego punktu znalezc wszystkich sasiadow w promieniu
    #   DBSCAN_PROMIEN. Przy gestosci skanu TLS (punkty co 1 cm) w promieniu
    #   25 cm siedzi ich kilka tysiecy. Dla 180 tys. punktow daje to setki
    #   milionow par i kilkanascie gigabajtow pamieci - program zostaje
    #   zabity przez system (kod wyjscia 137). Dokladnie to sie tu stalo.
    #
    #   Po przerzedzeniu do 5 cm zostaje kilkadziesiat tysiecy punktow,
    #   a pozycja pnia wyznaczona z nich jest IDENTYCZNA - bo liczy sie
    #   srodek skupiska, a nie liczba punktow w nim.
    #
    # Ustaw 0, zeby wylaczyc (tylko dla malych, rzadkich chmur).

    DBSCAN_PROMIEN = 0.15
    # Maksymalna odleglosc miedzy punktami, zeby uznac je za ten sam pien.
    # ZA MALA: jeden pien rozpadnie sie na kilka klastrow (bo TLS ma dziury).
    # ZA DUZA: dwa drzewa rosnace blisko sie zleja w jedno.
    # Zacznij od 0.25 m. Przy bardzo gestej chmurze mozesz zejsc do 0.15.

    DBSCAN_MIN_PUNKTOW = 25
    # Minimalna liczba punktow, zeby klaster byl uznany za pien.
    # ZA MALA: krzaki i galezie beda liczone jako drzewa.
    # ZA DUZA: zgubisz cienkie drzewka.

    MIN_SREDNICA_PNIA = 0.06     # 6 cm
    MAX_SREDNICA_PNIA = 1.20     # 120 cm
    # Filtr zdrowego rozsadku. Klaster o rozpietosci poza tym zakresem
    # to nie pien, tylko krzak (za maly) albo dwa zlane drzewa (za duzy).
    # To jest PROG GEOMETRYCZNY - mowi, czego algorytm ma w ogole szukac.
    # Czego ma Ci RAPORTOWAC, mowi parametr nizej. To nie to samo.

    MAX_PRZYROST_SREDNICY_CM_NA_M = 0.0   # 0 = FILTR WYLACZONY
    # SREDNICA PNIA MA MALEC KU GORZE. Jesli ROSNIE, to nie jest pien.
    #
    # Przez CALY lancuch okregow prowadzimy prosta srednica(wysokosc)
    # i patrzymy na jej nachylenie, w centymetrach na metr wysokosci.
    # Pien ma je UJEMNE - zweza sie ku gorze. Dodatnie znaczy, ze to, co
    # algorytm znalazl, robi sie z wysokoscia GRUBSZE - a takiego pnia nie
    # ma. To kepa osobnych obiektow, do ktorych dopasowano okregi na kilku
    # wysokosciach.
    #
    # ZMIERZONE na 107 drzewach, o ktorych wiem, ze sa prawdziwe:
    #       S1j (59 drzew z etykiet) : od -3.91 do -0.04 cm/m, mediana -1.04
    #       las testowy (18 drzew)   : od -1.63 do -1.58 cm/m
    #       las cienki (30 drzew)    : od -1.60 do -1.48 cm/m
    # Ani jedno nie mialo nachylenia dodatniego. Najgorsze bylo -0.04,
    # wiec prog +0.5 zostawia szeroki zapas.
    # Na poletkach z duzym podszytem: S2j 5 z 39, S4v 9 z 56.
    #
    # LICZYMY Z CALEGO LANCUCHA, NIE Z WYCINKA - i to jest wazne.
    # Pierwsza wersja brala nachylenie z okna 0.8-3.5 m, czyli z 10 okregow,
    # i odrzucala normalne drzewa. Przyklad z poletka S2o: srednice
    # 40.9 41.7 29.9 35.9 31.0 39.4 41.5 39.7 38.7 37.2 cm - ciag skacze
    # o 12 cm, a prosta przez niego ma nachylenie +0.4 cm/m. Przez cale
    # okno "pien urosl" o 1 cm przy wahaniach 12 cm. To nie jest dowod na
    # nic. Z calego lancucha (20+ okregow) szum sie usrednia i zostaje
    # prawdziwy trend.
    #
    # SPRAWDZONE I ODRZUCONE przy okazji: rozrzut srednic wzdluz lancucha
    # (odchylenie / srednia). Prog 0.19 trafial 7 z 30 prawdziwych drzew
    # w lesie cienkim - cienkie pnie maja z natury bardziej chybotliwy ciag
    # srednic, tak samo jak maja nizsza pustosc srodka. Nie uzywac.
    #
    # DLACZEGO DOMYSLNIE WYLACZONY (0), mimo ze na trzech zbiorach nic nie
    # kosztowal: na skanie ze Stonexa (poletko 9F, 42 mln punktow) wyrzucil
    # 9 z 57 wykryc, a to byly PRAWDZIWE drzewa. Przyczyna:
    #     drzewo 7, srednice od dolu [cm]:
    #       25 21 20 24 25 19 24 24 24 26 23 24   a potem   57  49
    # Pien jest poprawny przez 3 metry, ale dwa ostatnie okregi lancucha
    # przeskoczyly na galaz albo rozwidlenie przy nasadzie korony. Dwa zle
    # okregi na czternastu przeciagaja prosta i cale drzewo leci.
    #
    # Wersja odporna (mediana nachylen par, Theil-Sen) ratuje tylko 2 z 9,
    # bo na tym drzewostanie pnie prawie sie nie zwezaja w zakresie 0.5-6 m
    # i nie ma ujemnego sygnalu, ktory by te dwa odstajace okregi zrownowazyl.
    #
    # WLASCIWA NAPRAWA jest wczesniej: nie pozwolic lancuchowi przeskoczyc
    # na galaz. Srednica pnia nie moze sie podwoic na 25 cm wysokosci, wiec
    # taki skok powinien konczyc lancuch, a nie wchodzic do niego.
    # Do czasu, az to zrobie, filtr jest wylaczony.
    #
    # Kolumna nachylenie_srednicy_cm_na_m jest liczona ZAWSZE - mozesz
    # sprawdzic ja sam w 97_testuj_regule.py.
    #
    # UWAGA NA ROZWIDLENIA: pien dwuodnogowy tez moze dac skok srednicy.
    # Takie przypadki maja wypelniona kolumne grupa_rozwidlenia.

    SCIANA_MIN = 0.0      # 0 = WYLACZONE, patrz nizej
    # FILTR "CZY PIEN JEST SCIANA" - patrz funkcja policz_sciane().
    #
    # Skaner stoi w jednym miejscu, wiec prawdziwy pien widzi zawsze od tej
    # samej strony: na kazdej wysokosci swieca TE SAME sektory katowe.
    # Kepa podrostow daje okrag przypadkiem, z kilku osobnych patykow, a pol
    # metra wyzej stoja juz inne - sektory skacza.
    #
    # DLACZEGO AKURAT TO KRYTERIUM: jako jedyne z czterech sprawdzonych NIE
    # ZALEZY OD GRUBOSCI PNIA. Na sztucznym lesie pien 7 cm dostaje 1.000,
    # tak samo jak pien 50 cm. Pustosc srodka tego nie potrafi - tam cienki
    # pien fizycznie nie moze osiagnac wysokiego wyniku i ostry prog by go
    # wyciął.
    #
    # WYLACZONE (0) PO POMIARZE NA DRUGIM POLETKU Z REFERENCJA.
    # Prog 0.6 ustawilem na podstawie S1j, gdzie prawdziwe drzewa mialy
    # sciane od 0.93. Na poletku 9F (Stonex) prawdziwe drzewa maja ja
    # od 0.40 - bo skaner obszedl je pobieznie i na roznych wysokosciach
    # swiecily rozne strony pnia. Prog 0.6 odrzucil tam 1 wykrycie
    # i bylo to prawdziwe drzewo.
    # Kolumna sciana_pnia jest liczona ZAWSZE - sprawdz ja sam przez
    # 97_testuj_regule.py, zanim wlaczysz prog na swoich danych.
    #
    # ZMIERZONE na poletku S2o (40 wykrytych, 9 potwierdzonych przez 3DFin):
    #       potwierdzone : 0.741 - 1.000, mediana 0.917
    #       reszta       : 0.202 - 0.957, mediana 0.785
    #   prog 0.6 -> zostaje 29, wszystkie 9 potwierdzonych, nadmiar 20
    #   prog 0.7 -> zostaje 27, wszystkie 9 potwierdzonych, nadmiar 18
    # Prog 0.6 daje zapas do najgorszego potwierdzonego drzewa (0.741).
    # Podnoszac do 0.7 tniesz wiecej smieci, ale margines robi sie cienki.
    #
    # CO SPRAWDZILEM I ODRZUCILEM (zeby nie probowac drugi raz):
    #   - dlugosc lancucha: nie rozdziela, przy progu 18 plastrow zostaje
    #     3 potwierdzone i 7 nadmiarowych - czyli wyrzuca prawdziwe tak samo
    #     szybko jak smieci
    #   - sledzenie pnia do 12 m zamiast 6 m: poprawa mala, 9 potwierdzonych
    #     i 21 nadmiarowych
    #   - "czy nad pniem cos stoi": w gestym lesie przedluzenie dowolnej osi
    #     w gore trafia w czyjas korone (20.8 m kontra 18.8 m - bez roznicy)
    # Ustaw 0, zeby wylaczyc.

    SMUKLOSC_MIN = 25.0
    SMUKLOSC_MAX = 0.0    # 0 = WYLACZONE, patrz nizej
    # FILTR SMUKLOSCI - test zdrowego rozsadku na gotowym wierszu tabeli.
    #
    # Smuklosc (h/d) to wysokosc drzewa podzielona przez jego piersnice,
    # w tych samych jednostkach. Drzewo lesne ma 50-120. Sosna w zwarciu
    # 90-110, debe wolnostojacy 40-50.
    #
    # PO CO TO JEST: pipeline potrafil wypisac "drzewo" o wysokosci 4.8 m
    # i piersnicy 64 cm, czyli ze smukloscia 7.5. Czegos takiego w lesie
    # nie ma. Takie wiersze to albo falszywy okrag (nabieg korzeniowy,
    # lezacy kloc, dwa zlane pnie), albo PRAWDZIWE drzewo, ktoremu
    # segmentacja oddala korone sasiadowi i wysokosc wyszla za mala.
    # W obu przypadkach wiersz jest zly i do inwentaryzacji wejsc nie moze.
    #
    # SKAD TE LICZBY - zmierzone na 4 poletkach (195 drzew). Rozklad
    # smuklosci jest wyraznie DWUGARBNY, z dolkiem miedzy 30 a 40:
    #       h/d  10-30 : 29 drzew, srednio 6.5 m wysokosci i 38 cm piersnicy
    #       h/d  40-90 : 111 drzew, srednio 25 m wysokosci i 39 cm piersnicy
    # Prog 25 lezy bezpiecznie w dolku: usuwa grupe absurdow i nie wchodzi
    # w populacje prawdziwych drzew (ta zaczyna sie po 40).
    #
    # UWAGA, nie podnos tego do 60, mimo ze intuicja podpowiada inaczej
    # ("6 m i 10 cm = 60"). Przy progu 60 wylatuje 17 prawdziwych, grubych
    # drzew o h/d 40-60 - to normalne drzewa o rozpietej koronie.
    #
    # GORNY PROG JEST WYLACZONY (0), i to jest wynik pomiaru, nie wyboru.
    # Na poletku 9F (Stonex) odrzucil 3 wykrycia i WSZYSTKIE TRZY byly
    # prawdziwymi drzewami: 10 cm piersnicy przy 21 m wysokosci, 16 cm
    # przy 25 m. Smuklosc 150-215. Uznalem takie drzewa za niemozliwe na
    # podstawie poletka S1j, gdzie najsmuklejsze mialo 121 - ale tam byl
    # inny drzewostan. W zwarciu drzewa opanowane bywaja tak smukle.
    #
    # Odrzucone wiersze NIE GINA - ladują w pliku odrzucone_smuklosc.csv
    # w folderze skanu, z podana przyczyna. Mozesz je przejrzec i ocenic.
    # Ustaw 0, zeby wylaczyc filtr.

    MIN_DBH_RAPORTOWANIA = 0.07   # 7 cm
    # Drzewa o zmierzonej piersnicy MNIEJSZEJ niz tyle nie wchodza do tabeli.
    #
    # DLACZEGO OSOBNO OD MIN_SREDNICA_PNIA:
    #   Pomiar ma blad. Drzewo o prawdziwej piersnicy 7.0 cm moze sie zmierzyc
    #   jako 6.6 cm. Gdyby prog wykrywania i prog raportowania byly tym samym
    #   numerem, takie drzewo wypadaloby raz na dwa razy, zaleznie od szumu.
    #   Dlatego SZUKAMY od 6 cm (z zapasem w dol), a POKAZUJEMY od 7 cm.
    #
    # Ustaw --min-dbh 0 (z linii polecen), zeby zobaczyc wszystko, co pipeline
    # znalazl, razem z drobnica - przydatne, gdy sprawdzasz, czy nic nie ginie.
    #
    # Drzewa, ktorym piersnicy NIE UDALO SIE zmierzyc, zostaja w tabeli
    # (z adnotacja w kolumnie dbh_zrodlo_wartosci). Nie wiemy, czy sa grubsze
    # czy cienszy od progu, wiec ich wyrzucenie byloby zgadywaniem.

    MAX_WYDLUZENIE_PNIA = 3.0
    # Przekroj pnia widziany z gory jest w przyblizeniu kolisty, czyli ma
    # podobna szerokosc w kazdym kierunku. Jesli klaster jest 3x dluzszy niz
    # szerszy, to raczej lezaca galaz albo sciana - odrzucamy.

    # --- KROK 7: pomiar DBH -----------------------------------------
    DBH_WYSOKOSC = 1.3
    # Wysokosc pomiaru piersnicy nad gruntem. Standard w Europie: 1.3 m.
    # (W USA uzywa sie 1.37 m = 4.5 stopy.)

    DBH_GRUBOSC_PLASTRA = 0.10
    # Bierzemy punkty z przedzialu 1.3 +/- 0.05 m. Cienszy plaster = wierniejszy
    # pomiar, ale mniej punktow. 0.10 m to dobry kompromis.

    DBH_MIN_PUNKTOW = 10
    # Ponizej tylu punktow nie probujemy dopasowywac okregu - wynik bylby loteria.

    DBH_MAX_BLAD_DOPASOWANIA = 0.04
    # Kontrola jakosci. Po dopasowaniu okregu liczymy, jak daleko srednio leza
    # punkty od jego obwodu. Dla prawdziwego pnia na TLS to 3-15 mm.
    # Jesli wychodzi wiecej niz 40 mm, to znaczy, ze dopasowywalismy okrag do
    # czegos, co okregiem nie jest (galaz, dwa zlane pnie, punkty korony) -
    # i lepiej zwrocic "nie wiem" niz zmyslona liczbe.

    DETEKCJA_MAX_BLAD = 0.04
    DETEKCJA_MIN_PUSTOSC = 0.80
    # LUZNIEJSZE progi uzywane TYLKO do WYKRYWANIA pni (etap 1 kroku 5).
    #
    # DLACZEGO OSOBNE: wykrywanie i pomiar to dwa rozne pytania.
    #   wykrywanie: "czy stoi tu cos okraglego i pustego w srodku?"
    #   pomiar:     "jak dokladnie to cos ma srednicy?"
    # Mieszanie ich bylo bledem. Stosowanie progu pomiarowego (blad 40 mm) juz
    # na etapie wykrywania powodowalo, ze z 22 pni DOSKONALE widocznych na
    # 1.3 m - srednio 324 stopnie obwodu i 780 punktow - do lancuchow trafialo
    # tylko 11. Reszta byla odrzucana nie dlatego, ze jej nie bylo widac, tylko
    # dlatego, ze podszyt wokol niej psul pierwsze, zgrubne dopasowanie.
    #
    # SPRAWDZONE I ODRZUCONE: poluzowanie tych progow (blad 100 mm, pustosc
    # 0.65) dalo 69 drzew zamiast 37, a trafien w liste odniesienia tylko
    # o jedno wiecej (16 zamiast 15) - czyli same smieci. Dlatego wartosci
    # sa rowne progom pomiarowym. Parametry zostaja osobno, zeby dalo sie
    # szybko powtorzyc ten eksperyment na innym drzewostanie.

    RANSAC_PROBY = 500
    RANSAC_SZEROKOSC = 0.02
    RANSAC_KARA_SRODEK = 3.0
    RANSAC_MAX_ODCHYLKA_OSI = 0.08
    # Parametry dopasowania okregu odpornego na podszyt - patrz dlugi
    # komentarz w dopasuj_okrag_ransac().
    #   PROBY        - ile razy losowac trojki punktow. Wiecej = pewniej, wolniej.
    #   SZEROKOSC    - jak blisko okregu musi lezec punkt, zeby sie liczyl [m]
    #   KARA_SRODEK  - ile razy bardziej boli punkt w srodku niz pomaga punkt
    #                  na obwodzie. To zmusza algorytm do szukania PUSTYCH rur.
    #   MAX_ODCHYLKA_OSI - o ile srodek okregu moze odbiec od osi pnia [m].
    #                  Najwazniejszy z czworki: przy 0.40 m piersnice wychodzily
    #                  +12 cm za grube, przy 0.08 m tylko +2.6 cm.

    KORYGUJ_NACHYLENIE = True
    # Czy poprawiac srednice o kat pochylenia pnia. Patrz dlugi komentarz
    # w kroku 5. Ustaw False, zeby dostac surowe srednice z plastrow
    # poziomych (np. gdy chcesz porownac z inna metoda, ktora tego nie robi).

    MARTWE_PROG_UDZIALU_GORY = 0.03
    MARTWE_PROG_PROMIENIA_M = 1.0
    # Kiedy uznac drzewo za PRAWDOPODOBNIE MARTWE (posusz stojacy).
    # Zywe drzewo ma nad soba korone: duzo punktow w gornej czesci i szeroko
    # rozrzuconych. Zlamany, martwy pien nie ma nic - tylko slup.
    # Liczymy wiec dwie rzeczy w gornych 40% wysokosci drzewa:
    #   - jaka czesc punktow drzewa tam jest
    #   - jak szeroko sa rozrzucone wokol osi
    # Jesli OBIE sa male - to prawdopodobnie posusz.
    #
    # UWAGA: to jest HEURYSTYKA, nie pewnik. Drzewo zaslonite przez sasiada
    # albo stojace na skraju skanu tez moze miec malo punktow u gory.
    # Traktuj te kolumne jako podpowiedz do sprawdzenia, nie jako wyrok.

    ROZWIDLENIE_MAX_ODLEGLOSC_M = 0.4
    ROZWIDLENIE_WYSOKOSC_SPRAWDZENIA_M = 0.5
    # Wykrywanie pni rozwidlonych. Dwie odnogi tego samego drzewa maja osie,
    # ktore IM NIZEJ, TYM BARDZIEJ SIE ZBLIZAJA - bo schodza sie do wspolnej
    # podstawy. Przedluzamy wiec osie obu pni w dol do tej wysokosci i
    # sprawdzamy, czy sa blizej siebie niz ROZWIDLENIE_MAX_ODLEGLOSC_M.
    # Jesli tak - to jedno drzewo o dwoch odnogach, a nie dwa drzewa.

    DBH_TOLERANCJA_WYSOKOSCI = 0.3
    # O ile metrow okrag moze odbiegac od 1.3 m, zeby uznac go za POMIAR
    # piersnicy. 0.3 m to +/- jeden plaster z zapasem.

    DBH_MAX_EKSTRAPOLACJA = 0.0
    DBH_MIN_OKREGOW_DO_EKSTRAPOLACJI = 5
    # PRZEDLUZANIE ZBIEZYSTOSCI W DOL - DOMYSLNIE WYLACZONE (0.0).
    #
    # Pomysl byl taki: pien zweza sie ku gorze regularnie, wiec majac
    # kilkanascie srednic z lancucha mozna dopasowac prosta i odczytac ja
    # na 1.3 m, tak jak lesnik szacuje piersnice, gdy nie da sie dojsc
    # do drzewa. Brzmi rozsadnie. ZMIERZYLEM TO I NIE DZIALA.
    #
    # Test (9F, 62 drzewa z piersnica ZMIERZONA): ucinamy lancuch od dolu,
    # przedluzamy prosta do 1.3 m i porownujemy z tym, co naprawde
    # zmierzono na 1.3 m:
    #
    #      lancuch od     drzew    blad sredni    RMSE      najgorsze
    #        1.8 m          52       -2.4 cm      5.5 cm     21.3 cm
    #        2.1 m          49       -2.6 cm      6.4 cm     26.6 cm
    #        2.5 m          45       -3.0 cm      9.0 cm     33.3 cm
    #        3.0 m          40       -3.9 cm     11.5 cm     40.8 cm
    #
    # Dla porownania piersnica ZMIERZONA ma na tej samej powierzchni
    # RMSE 2.8 cm. W granicach +/- 3 cm miesci sie tylko polowa oszacowan.
    #
    # Blad 33 cm na pojedynczym drzewie jest nie do wykrycia golym okiem
    # w tabeli, a wchodzi do pola przekroju z kwadratem. Puste pole jest
    # uczciwsze niz taka liczba. Zamiast zgadywac, pipeline:
    #   - probuje DOCIAGNAC LANCUCH w dol realnym pomiarem (etap 2.7),
    #   - a gdy sie nie da, zostawia dbh_m puste i podaje srednice
    #     NAPRAWDE zmierzona wraz z wysokoscia, na ktorej ja zmierzyl
    #     (kolumny srednica_zmierzona_m i wysokosc_pomiaru_m).
    #
    # Gdybys mimo wszystko chcial oszacowania - ustaw tu np. 0.8. Wartosc
    # trafi do dbh_szacowany_m i dbh_do_uzycia_m, nigdy do dbh_m, a kolumna
    # dbh_zrodlo_wartosci powie "oszacowanie_ze_zbieznosci". Pamietaj wtedy
    # o liczbach z tabeli wyzej.

    # --- DOCIAGANIE LANCUCHA W DOL (etap 2.7) ------------------------
    DOCIAGAJ_LANCUCH_W_DOL = True
    # Gdy lancuch okregow nie schodzi do piersnicy, sprobuj domierzyc go
    # w dol plaster po plastrze, kotwiczac srodek na osi pnia. Szczegoly
    # i wyniki pomiarow - w komentarzu przy etapie 2.7.
    DOCIAGANIE_DOL = 1.0            # ponizej tej wysokosci nie schodzimy
    DOCIAGANIE_MAX_PLASTROW = 14    # najwyzej tyle ogniw mozna dolozyc
    DOCIAGANIE_OKNO = 2.0           # z ilu metrow lancucha liczymy os i promien
    DOCIAGANIE_PIERSCIEN = 0.10     # szerokosc pierscienia wokol spodziewanego r
    DOCIAGANIE_MAX_ROZNICA_R = 0.06
    # Najwazniejsze zabezpieczenie: nowy promien nie moze odbiec od
    # spodziewanego o wiecej niz tyle. Na 9F drzewo 74 zatrzymalo sie na tym
    # natychmiast (pierscien dal 8.1 cm zamiast 28.0) - i slusznie, bo ponizej
    # 2.1 m ten pien jest splatany z sasiadem.
    DOCIAGANIE_MAX_ODCHYLKA_OSI = 0.06
    DOCIAGANIE_MAX_BLAD = 0.02
    DOCIAGANIE_MIN_PUSTOSC = 0.80
    DOCIAGANIE_MIN_POKRYCIE = 90.0
    # Pokrycie LUZNIEJSZE niz przy wykrywaniu (tam 90 st. przy szukaniu
    # i 180 st. przy pomiarze) - i to jest celowe, nie niedopatrzenie.
    # Przez krotki luk o NIEZNANYM srodku przechodzi nieskonczenie wiele
    # okregow o roznych promieniach - dlatego przy wykrywaniu luk 120 st.
    # jest bezwartosciowy. Tutaj srodek jest PRZYBITY osia kilkunastu
    # okregow powyzej, wiec ten sam luk wyznacza promien jednoznacznie.

    DBH_MIN_PUSTOSC = 0.80
    # NAJSKUTECZNIEJSZY TEST "PIEN CZY KRZAK". Jaka czesc punktow musi lezec
    # na obwodzie, a nie w srodku okregu. Patrz dlugi komentarz w funkcji
    # dopasuj_okrag_odpornie().
    #   1.00 = idealny pusty pierscien (pien)
    #   0.70 = bryla wypelniona punktami (krzak, kepa galezi)
    # Na danych rzeczywistych pnie mialy 0.99-1.00, krzaki mediane 0.73,
    # wiec prog 0.80 rozdziela je z duzym zapasem.
    # Obnizaj ostroznie - to jedyna rzecz, ktora trzyma krzaki poza tabela.
    #
    # NIE PODNOS TEGO PROGU WYSOKO, i to jest ZMIERZONE, nie przypuszczenie.
    # Pustosc, jaka pien moze w ogole osiagnac, ZALEZY OD JEGO GRUBOSCI, bo
    # szum skanera (kilka mm) jest staly, a promien pnia nie. Na sztucznym
    # lesie cienkim wyszlo tak:
    #       pnie  7-9  cm:  pustosc 0.924 - 0.932
    #       pnie  9-12 cm:  pustosc 0.959 - 0.992
    #       pnie 12-16 cm:  pustosc 0.975 - 0.996
    #       pnie 16-20 cm:  pustosc 0.997 - 1.000
    # Czyli prog 0.99 - ktory na drzewostanie GRUBYM pieknie czysci tabele
    # (na poletku S2o: 40 drzew -> 26, i zadnego potwierdzonego nie gubi) -
    # wyrzucilby KAZDY pien cienszy niz ~16 cm. Dlatego gdyby kiedys
    # podnosic ten prog, to tylko jako FUNKCJE PROMIENIA, nie jedna liczba.

    DETEKCJA_MIN_POKRYCIE_KATOWE = 90.0
    # Prog pokrycia przy WYKRYWANIU pnia - luzny, celowo.
    #
    # ZASADA: SZUKAJ HOJNIE, MIERZ SUROWO. Lepiej znalezc drzewo i napisac
    # "piersnicy nie wiem", niz w ogole go nie zauwazyc. Brakujacego drzewa
    # nie odzyskasz, a brakujaca piersnice mozna dopisac pozniej.
    #
    # ZMIERZONE na poletku 9F (Stonex, 62 drzewa z referencji):
    #       prog 180 st.: znalezione 40 z 62  -> czulosc 64.5%
    #       prog  90 st.: znalezione 59 z 62  -> czulosc 95.2%
    # Prawdziwe drzewa mialy tam pokrycie od 163 stopni, wiec prog 180
    # wycinal je wprost. Na poletku S1j (obchodzonym dokladnie, pokrycie
    # od 309 stopni) prog 180 nic nie kosztowal - i wlasnie dlatego
    # ustawilem go wtedy za wysoko.

    DBH_MIN_POKRYCIE_KATOWE = 180.0
    # Minimalny kat (w stopniach), na jakim punkty musza otaczac pien.
    #
    # BYLO 90 STOPNI I TO BYL BLAD, oparty na zlym zalozeniu. Zakladalem skan
    # ze STATYWU, z jednego miejsca - wtedy skaner widzi tylko blizsza strone
    # pnia i przekroj jest polksiezycem, 90-180 stopni. Potem zmierzylem
    # pokrycie katowe w prawdziwych danych i okazalo sie, ze skaner byl
    # MOBILNY, obnoszony po powierzchni:
    #       S1j: mediana 360 stopni, 93% okregow powyzej 300
    #       S4v: mediana 280
    #       S2j: mediana 240
    #       S2o: mediana 220
    # Pien widziany DOOKOLA to zupelnie inna sytuacja niz polksiezyc, a prog
    # 90 stopni przepuszczal przy tym cwiartki okregu - czyli dokladnie to,
    # czym kepa galezi udaje pien.
    #
    # ILE WYNOSI NAPRAWDE: na poletku S1j, gdzie znam prawde z etykiet,
    # 59 PRAWDZIWYCH drzew ma pokrycie od 288 do 360 stopni (mediana 358),
    # a jedyne falszywe wykrycie ma 167. Prog 200 rozdziela je bezblednie.
    #
    # DLACZEGO MIMO TO 180, A NIE 250: pokrycie zalezy od tego, JAK DOKLADNIE
    # obeszlo sie powierzchnie, a nie od drzewa. Na poletku obchodzonym
    # pobieznie prawdziwe drzewa tez beda mialy mniej. 180 stopni to prog
    # uzasadniony geometrycznie, nie dopasowany do jednego poletka: ponizej
    # polowy obwodu promien okregu przestaje byc wyznaczony stabilnie.
    #
    # Jesli Twoje dane sa z porzadnie obchodzonej powierzchni (sprawdz
    # kolumne dbh_pokrycie_katowe_deg - mediana ponad 300), smialo podnies
    # do 250. Jesli to skan ze statywu z jednego miejsca, obniz do 90.
    # DLACZEGO TO WAZNE: jesli skaner widzial pien tylko z jednej strony,
    # masz krotki lucz. Do krotkiego lucza da sie dopasowac i maly okrag,
    # i gigantyczny - matematyka nie rozstrzygnie. Takie pomiary trzeba
    # oznaczyc jako niepewne, a nie wpisywac do tabeli jak pewne.

    # --- KROK 6: segmentacja ----------------------------------------
    MAX_ODLEGLOSC_OD_PNIA = 8.0
    # Punkt dalej niz tyle metrow (w poziomie) od najblizszego pnia nie zostanie
    # przypisany do zadnego drzewa. Dopasuj do szerokosci koron w swoim lesie.

    # --- KROK 6b: segmentacja metoda grafowa -------------------------
    GRAF_ROZMIAR_VOXELA = 0.30
    # Metoda grafowa jest ciezka obliczeniowo, wiec najpierw zmniejszamy
    # chmure: dzielimy przestrzen na szescianiki o tym boku i kazdy zastepujemy
    # jednym punktem. 0.3 m to dobry kompromis. Mniejszy = dokladniej i wolniej.

    GRAF_MAX_DLUGOSC_KRAWEDZI = 1.0
    # Dwa voxele sa ze soba "polaczone" tylko jesli sa blizej niz tyle metrow.
    # To decyduje, przez co sciezka moze przejsc.
    # ZA DUZA: sciezka przeskoczy przez powietrze z korony jednego drzewa do
    #   drugiego i metoda przestanie dzialac lepiej niz prosta.
    # ZA MALA: korona rozpadnie sie na kawalki niepolaczone z pniem i duza
    #   czesc punktow zostanie nieprzypisana.
    # Musi byc wieksza od GRAF_ROZMIAR_VOXELA * 1.8, inaczej nawet sasiadujace
    # voxele nie beda polaczone po skosie.
    #
    # UWAGA, PULAPKA: podnoszenie tego parametru NIC NIE DA, jesli
    # GRAF_SASIEDZI jest za male - patrz komentarz ponizej. Ja sie na tym
    # zlapalem przy budowaniu tego skryptu: zmieniałem 0.75 -> 1.0 -> 1.2
    # i wyniki byly co do cyfry identyczne.

    GRAF_SASIEDZI = 20
    # Ilu najblizszych sasiadow rozwazamy dla kazdego voxela przy budowie grafu.
    #
    # TO JEST WAZNIEJSZE, NIZ WYGLADA. Dla kazdego voxela patrzymy tylko na
    # GRAF_SASIEDZI najblizszych - i tylko wsrod nich szukamy krawedzi. W
    # gestej chmurze tych 12 najblizszych lezy w promieniu moze 0.5 m, wiec
    # ZADNA dluzsza krawedz nie ma szansy powstac, choćby GRAF_MAX_DLUGOSC
    # pozwalal na 1.2 m. Efekt: przerwy w pniu (a maja one zwykle 0.5-0.7 m,
    # bo skaner nie widzi calego pnia) nie zostaja przeskoczone, korona nad
    # przerwa jest odcieta od pnia i drzewo gubi wlasny czubek.
    #
    # Na danych testowych: k=12 dawalo 97.5% voxeli osiagnietych i blad
    # wysokosci RMSE 1.53 m; k=20 dalo 100% i RMSE 1.06 m. Powyzej k=20
    # nic sie nie zmienilo, tylko graf zrobil sie wiekszy.
    #
    # Jesli w logu KROKU 6b widzisz duzo voxeli nieosiagalnych - PODNIES TO.

    GRAF_KARA_POZIOMA = 4.0
    # KARA ZA PRZEMIESZCZANIE SIE W POZIOMIE. To drugi najwazniejszy parametr.
    #
    # PROBLEM, ktory rozwiazuje: czubek 26-metrowego drzewa jest w linii
    # sciezki prawie tak samo daleko od wlasnego pnia (26 m w dol) jak od pnia
    # sasiada (tez ~26 m w dol). Przy rownych kosztach decyduje przypadek -
    # i wysokie drzewa gubia wlasne czubki.
    #
    # ROZWIAZANIE: liczymy dlugosc krawedzi tak, jakby ruch w poziomie byl
    # KARA_POZIOMA razy "drozszy" niz ruch w pionie:
    #     koszt = sqrt(KARA * (dx^2 + dy^2) + dz^2)
    # Schodzenie prosto w dol po wlasnym pniu jest wtedy tanie, a przeskok
    # w bok do korony sasiada - kosztowny. Dokladnie tak, jak powinno byc:
    # punkt nalezy do drzewa, ktore jest POD NIM, nie obok.
    #
    # 1.0 = brak kary (czysta geometria). 4.0 dziala dobrze. Powyzej ~10
    # metoda zaczyna sie zachowywac jak zwykle ciecie pionowe.


P = Parametry()


# ======================================================================
# KROK 1: WCZYTANIE
# ======================================================================
def krok1_wczytaj(sciezka):
    """
    Wczytuje plik .las/.laz i zwraca tablice wspolrzednych Nx3.

    Co to jest .laz:
        To spakowany .las - standardowy format chmur punktow. Wewnatrz
        wspolrzedne sa trzymane jako liczby calkowite plus wspolczynnik skali,
        zeby plik byl mniejszy. laspy rozpakowuje to za nas: las.x, las.y, las.z
        daja juz gotowe metry.
    """
    print(f"\n[KROK 1] Wczytuje {sciezka.name}")
    las = laspy.read(str(sciezka))

    punkty = np.column_stack([
        np.asarray(las.x, dtype=np.float64),
        np.asarray(las.y, dtype=np.float64),
        np.asarray(las.z, dtype=np.float64),
    ])

    print(f"         punktow: {len(punkty):,}")
    print(f"         zasieg X: {punkty[:,0].min():.2f} - {punkty[:,0].max():.2f} m")
    print(f"         zasieg Y: {punkty[:,1].min():.2f} - {punkty[:,1].max():.2f} m")
    print(f"         zasieg Z: {punkty[:,2].min():.2f} - {punkty[:,2].max():.2f} m")

    powierzchnia = ((punkty[:, 0].max() - punkty[:, 0].min()) *
                    (punkty[:, 1].max() - punkty[:, 1].min()))
    print(f"         gestosc: {len(punkty)/max(powierzchnia,1):.0f} pkt/m2")

    # --- przerzedzenie wejsciowe ---
    if P.VOXEL_WEJSCIOWY and P.VOXEL_WEJSCIOWY > 0:
        przed = len(punkty)

        # JEDEN KLUCZ ZAMIAST TRZECH KOLUMN - i to jest roznica miedzy
        # "dziala" a "program zostal zabity".
        #
        # Wczesniej bylo np.unique(klucze, axis=0), gdzie klucze to tablica
        # N x 3. Taki unique musi posortowac wiersze, a do tego robi po
        # drodze kilka kopii calej tablicy. Przy 38 mln punktow (skan ze
        # Stonexa, 24 tys. pkt/m2) to kilka gigabajtow i system zabija
        # program jeszcze w kroku 1. Przy 15 mln przechodzilo, wiec blad
        # ujawnil sie dopiero na gestszym skanerze.
        #
        # Teraz pakujemy trzy numery voxela w JEDNA liczbe calkowita:
        # po 21 bitow na os, co przy voxelu 1 cm daje zasieg +/- 10 km -
        # z duzym zapasem na kazda powierzchnie probna. np.unique na
        # jednej kolumnie jest kilkanascie razy lzejszy.
        srodek = punkty.min(axis=0)
        kl = np.floor((punkty - srodek) / P.VOXEL_WEJSCIOWY).astype(np.int64)
        if kl.max() >= 2 ** 21:
            # Powierzchnia wieksza niz 21 bitow na os - wracamy do wersji
            # wolniejszej, ale zawsze poprawnej.
            _, pierwszy = np.unique(kl, axis=0, return_index=True)
        else:
            klucz = (kl[:, 0] << 42) | (kl[:, 1] << 21) | kl[:, 2]
            del kl
            _, pierwszy = np.unique(klucz, return_index=True)
            del klucz
        punkty = punkty[np.sort(pierwszy)]
        del pierwszy
        print(f"         przerzedzenie do voxela {P.VOXEL_WEJSCIOWY} m: "
              f"{przed:,} -> {len(punkty):,} ({len(punkty)/przed*100:.1f}%)")

    return punkty, las


# ======================================================================
# KROK 2: USUNIECIE SZUMU
# ======================================================================
def krok2_usun_szum(punkty):
    """
    Filtr SOR - Statistical Outlier Removal.

    POMYSL W JEDNYM ZDANIU:
        Prawdziwe punkty maja bliskich sasiadow. Szum jest samotny.

    JAK TO LICZYMY:
        1. Dla kazdego punktu znajdz k najblizszych sasiadow.
        2. Policz sredania odleglosc do nich. To miara "jak gesto tu jest".
        3. Punkty, u ktorych ta srednia jest nienormalnie duza (odstaje od
           sredniej calej chmury o wiecej niz N odchylen standardowych),
           sa samotne -> to szum -> wyrzucamy.

    UWAGA - typowa pulapka:
        Czubki drzew i cienkie galazki tez maja malo sasiadow! Jesli ustawisz
        prog za agresywnie (SOR_PROG_ODCHYLEN np. 1.5), filtr zje Ci wierzcholki
        i wysokosci drzew wyjda za male. Zawsze sprawdz w CloudCompare, co
        zostalo usuniete, zanim zaufasz wynikom.
    """
    print(f"\n[KROK 2] Usuwam szum (SOR, k={P.SOR_SASIEDZI}, "
          f"prog={P.SOR_PROG_ODCHYLEN} sigma)")

    drzewo_kd = cKDTree(punkty)
    # k+1 bo pierwszym "sasiadem" kazdego punktu jest on sam (odleglosc 0)
    # Pytamy PARTIAMI, a nie o cala chmure naraz. Przy 20 mln punktow i 13
    # sasiadach tablica odpowiedzi to 20e6 x 13 odleglosci PLUS tyle samo
    # numerow sasiadow - razem kilka gigabajtow, i program zostaje zabity
    # przez system (to sie wlasnie stalo na pliku z 26.8 mln punktow).
    # Partiami zuzycie pamieci jest stale, a wynik dokladnie ten sam, bo
    # kazdy punkt i tak pytany jest osobno o te same drzewo kd.
    PARTIA = 2_000_000
    srednie_odlegosci = np.empty(len(punkty), dtype=np.float32)
    for poczatek in range(0, len(punkty), PARTIA):
        koniec = min(poczatek + PARTIA, len(punkty))
        odl, _ = drzewo_kd.query(punkty[poczatek:koniec],
                                 k=P.SOR_SASIEDZI + 1, workers=-1)
        srednie_odlegosci[poczatek:koniec] = odl[:, 1:].mean(axis=1)
        del odl
    if len(punkty) > PARTIA:
        print(f"         (liczone w {int(np.ceil(len(punkty)/PARTIA))} "
              f"partiach, zeby zmiescic sie w pamieci)")

    prog = srednie_odlegosci.mean() + P.SOR_PROG_ODCHYLEN * srednie_odlegosci.std()
    zostaw = srednie_odlegosci < prog

    usuniete = (~zostaw).sum()
    print(f"         srednia odleglosc do sasiada: {srednie_odlegosci.mean()*100:.1f} cm")
    print(f"         prog odciecia: {prog*100:.1f} cm")
    print(f"         usuniete: {usuniete:,} punktow "
          f"({usuniete/len(punkty)*100:.2f}%)")

    return punkty[zostaw], zostaw


# ======================================================================
# KROK 3: GRUNT I MODEL TERENU
# ======================================================================
def rozrost_gruntu(siatka, jest_dana, max_skok):
    """
    Wybiera komorki, w ktorych skaner NAPRAWDE widzial grunt.

    Zwraca tablice logiczna tego samego ksztaltu co siatka.

    POMYSL:
        Prawdziwy teren jest GLADKI I SPOJNY - idac po nim, nigdy nie
        przeskakujesz nagle o kilka metrow. Komorki, w ktorych "najnizszy
        punkt" to korona 20 m nad ziemia, takiej gladkiej calosci nie tworza:
        jedna ma 6 m, sasiednia 20, nastepna 9 - bo to przypadkowe kawalki
        galezi na roznych wysokosciach.

        Wiec: polacz ze soba kazde dwie SASIADUJACE komorki, ktore roznia sie
        wysokoscia o mniej niz max_skok. Powstanie kilka osobnych "wysp".
        Grunt to NAJWIEKSZA z nich.

    DLACZEGO NIE ROSNE PO PROSTU OD NAJNIZSZEJ KOMORKI:
        Bo probowalem i to nie dziala. Najnizszy punkt skanu potrafi lezec
        w dziurze - w zaglebieniu przy korzeniu albo w resztce szumu pod
        gruntem. Jego sasiedzi sa wtedy o metr wyzej, rozrost zatrzymuje sie
        po dwoch komorkach i caly DTM leci w kosmos. Szukanie najwiekszej
        wyspy nie ma tej slabosci, bo nie zalezy od zadnego pojedynczego
        punktu startowego.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    n_wie, n_kol = siatka.shape
    przyjete = np.zeros(siatka.shape, dtype=bool)
    if not jest_dana.any():
        return przyjete

    numer = np.arange(n_wie * n_kol).reshape(n_wie, n_kol)
    zrodla, cele = [], []

    # Cztery kierunki wystarcza - polaczenie jest nieskierowane, wiec
    # para (w prawo) pokrywa tez (w lewo) z drugiej strony.
    przesuniecia = [(0, 1), (1, 0), (1, 1), (1, -1)]

    for dw, dk in przesuniecia:
        # wycinki tablicy przesuniete wzgledem siebie o (dw, dk)
        w_od, w_do = max(0, -dw), n_wie - max(0, dw)
        k_od, k_do = max(0, -dk), n_kol - max(0, dk)

        a = (slice(w_od, w_do), slice(k_od, k_do))
        b = (slice(w_od + dw, w_do + dw), slice(k_od + dk, k_do + dk))

        oba_sa = jest_dana[a] & jest_dana[b]
        # errstate: puste komorki maja inf, a inf-inf daje NaN i ostrzezenie.
        # NaN i tak nie przejdzie testu <=, a oba_sa je odfiltruje.
        with np.errstate(invalid="ignore"):
            plynnie = np.abs(siatka[a] - siatka[b]) <= max_skok
        polaczone = oba_sa & plynnie

        zrodla.append(numer[a][polaczone])
        cele.append(numer[b][polaczone])

    zrodla = np.concatenate(zrodla) if zrodla else np.array([], dtype=int)
    cele = np.concatenate(cele) if cele else np.array([], dtype=int)

    graf = coo_matrix((np.ones(len(zrodla)), (zrodla, cele)),
                      shape=(n_wie * n_kol, n_wie * n_kol))
    ile, etykiety = connected_components(graf, directed=False)

    # Wyspy liczymy tylko wsrod komorek, ktore maja dane.
    etykiety_2d = etykiety.reshape(n_wie, n_kol)
    etyk_danych = etykiety_2d[jest_dana]
    unikalne, liczebnosc = np.unique(etyk_danych, return_counts=True)

    najwieksza = unikalne[np.argmax(liczebnosc)]
    przyjete = jest_dana & (etykiety_2d == najwieksza)

    posortowane = np.sort(liczebnosc)[::-1][:3]
    print(f"         wysp terenu: {len(unikalne)}, "
          f"trzy najwieksze: {list(posortowane)} komorek")

    return przyjete


def krok3_model_terenu(punkty):
    """
    Buduje DTM - Digital Terrain Model, czyli mape wysokosci samego gruntu.

    PO CO TO:
        Zeby zmierzyc wysokosc drzewa, musisz wiedziec, gdzie jest ziemia POD
        TYM KONKRETNYM DRZEWEM. Na zboczu grunt moze sie roznic o kilka metrow
        miedzy jednym koncem poletka a drugim. Bez DTM wysokosci beda bezsensowne.

    METODA (najnizszy punkt w komorce siatki):
        1. Naloz na poletko siatke kwadratow o boku DTM_ROZMIAR_KOMORKI.
        2. W kazdym kwadracie znajdz najnizszy punkt. To KANDYDAT na grunt.
        3. Odrzuc kandydatow, ktorzy sa za wysoko w stosunku do szerszego
           otoczenia (zabezpieczenie nr 1) - to komorki, w ktorych skaner
           wcale nie widzial ziemi.
        4. Odrzuc kandydatow wyraznie wyzszych od najblizszych sasiadow
           (zabezpieczenie nr 2) - klody, kopce, krzaki.
        5. Zinterpoluj gladka powierzchnie miedzy pozostalymi.

        To prosta metoda, ale na TLS dziala dobrze, bo skaner stoi na ziemi
        i widzi ja gesto. Dla danych lotniczych (ALS) uzywa sie bardziej
        zaawansowanych algorytmow (np. Cloth Simulation Filter).
    """
    from scipy.ndimage import minimum_filter

    print(f"\n[KROK 3] Buduje model terenu (komorka {P.DTM_ROZMIAR_KOMORKI} m)")

    x, y, z = punkty[:, 0], punkty[:, 1], punkty[:, 2]
    x_min, y_min = x.min(), y.min()

    # Numer komorki (kolumna, wiersz) dla kazdego punktu
    kol = ((x - x_min) / P.DTM_ROZMIAR_KOMORKI).astype(np.int64)
    wie = ((y - y_min) / P.DTM_ROZMIAR_KOMORKI).astype(np.int64)
    n_kol, n_wie = kol.max() + 1, wie.max() + 1

    # Najnizszy Z w kazdej komorce, jako tablica 2D (NaN = komorka pusta).
    # np.minimum.at robi to w jednym przebiegu, bez petli po komorkach.
    siatka = np.full((n_wie, n_kol), np.inf)
    np.minimum.at(siatka, (wie, kol), z)
    jest_dana = np.isfinite(siatka)

    print(f"         siatka: {n_kol} x {n_wie} komorek, "
          f"{jest_dana.sum():,} z danymi")

    # --- ZABEZPIECZENIE NR 1: rozrost od najnizszej komorki --------------
    # Patrz komentarz przy DTM_MAX_SKOK_MIEDZY_KOMORKAMI.
    wiarygodne_1 = rozrost_gruntu(siatka, jest_dana,
                                  P.DTM_MAX_SKOK_MIEDZY_KOMORKAMI)

    odrzucone_1 = int(jest_dana.sum() - wiarygodne_1.sum())
    print(f"         zabezpieczenie 1 (rozrost, max skok "
          f"{P.DTM_MAX_SKOK_MIEDZY_KOMORKAMI} m): odrzucono {odrzucone_1:,} "
          f"z {int(jest_dana.sum()):,} komorek - tam gruntu nie widac")

    # Przejscie z tablicy 2D na liste punktow (srodek komorki + wysokosc)
    wie_ok, kol_ok = np.nonzero(wiarygodne_1)
    min_z = siatka[wie_ok, kol_ok]
    cx = (kol_ok + 0.5) * P.DTM_ROZMIAR_KOMORKI + x_min
    cy = (wie_ok + 0.5) * P.DTM_ROZMIAR_KOMORKI + y_min

    if len(min_z) < 4:
        raise RuntimeError(
            "Po filtracji zostalo za malo komorek gruntu. Zwieksz "
            "DTM_MAX_NAD_OTOCZENIEM albo DTM_ROZMIAR_KOMORKI.")

    # --- ZABEZPIECZENIE NR 2: porownanie z najblizszymi sasiadami --------
    kd = cKDTree(np.column_stack([cx, cy]))
    _, sasiedzi = kd.query(np.column_stack([cx, cy]),
                           k=min(9, len(min_z)), workers=-1)
    mediana_sasiadow = np.median(min_z[sasiedzi], axis=1)
    wiarygodne_2 = (min_z - mediana_sasiadow) < P.DTM_MAX_ROZNICA_SASIADA

    print(f"         zabezpieczenie 2: odrzucono {int((~wiarygodne_2).sum()):,} "
          f"komorek (klody/krzaki)")

    cx, cy, min_z = cx[wiarygodne_2], cy[wiarygodne_2], min_z[wiarygodne_2]

    if len(min_z) < 4:
        raise RuntimeError(
            "Zbyt malo punktow gruntu, zeby zbudowac DTM. "
            "Zwieksz DTM_ROZMIAR_KOMORKI albo sprawdz, czy chmura zawiera grunt."
        )

    print(f"         grunt: {min_z.min():.2f} - {min_z.max():.2f} m "
          f"(deniwelacja {min_z.max()-min_z.min():.2f} m)")

    zasieg = ((cx.max() - cx.min()) * (cy.max() - cy.min()))
    print(f"         obszar z widocznym gruntem: ok. {len(min_z)*P.DTM_ROZMIAR_KOMORKI**2:.0f} m2")

    return np.column_stack([cx, cy]), min_z


def krok4_normalizuj_wysokosc(punkty, dtm_xy, dtm_z):
    """
    Dla kazdego punktu liczy jego wysokosc NAD GRUNTEM.

    To jedna linijka matematyki: z_nad_gruntem = z_punktu - z_gruntu(x, y)
    ...tylko trzeba najpierw wyliczyc z_gruntu w dowolnym (x, y) - przez
    interpolacje miedzy punktami DTM.

    Po tym kroku grunt lezy na wysokosci 0 i wszystko staje sie proste:
    "plaster pni na 1.3 m" to po prostu punkty z z_nad_gruntem w okolicy 1.3.
    """
    print(f"\n[KROK 4] Normalizuje wysokosci wzgledem gruntu")

    # linear = gladka interpolacja miedzy punktami DTM
    z_gruntu = griddata(dtm_xy, dtm_z, punkty[:, :2], method="linear")

    # Na samych brzegach poletka interpolacja liniowa nie dziala (brak otoczenia),
    # wiec tam uzupelniam metoda "najblizszy sasiad".
    braki = np.isnan(z_gruntu)
    if braki.any():
        z_gruntu[braki] = griddata(dtm_xy, dtm_z, punkty[braki, :2],
                                   method="nearest")
        print(f"         brzegi uzupelnione metoda nearest: {braki.sum():,} pkt")

    wysokosc_nad_gruntem = punkty[:, 2] - z_gruntu
    print(f"         wysokosc nad gruntem: {wysokosc_nad_gruntem.min():.2f} - "
          f"{wysokosc_nad_gruntem.max():.2f} m")

    return wysokosc_nad_gruntem, z_gruntu


# ======================================================================
# KROK 5: DETEKCJA PNI
# ======================================================================
def oblicz_pionowosc(punkty, k_sasiadow):
    """
    Dla kazdego punktu zwraca |skladowa Z wektora normalnego| powierzchni,
    na ktorej ten punkt lezy.

    Interpretacja wyniku:
        bliskie 0  -> powierzchnia PIONOWA  (scianka pnia)
        bliskie 1  -> powierzchnia POZIOMA  (ziemia, gorna strona galezi)

    Metoda: PCA na sasiedztwie punktu. Chmurka sasiadow ma jakis ksztalt;
    kierunek, w ktorym jest NAJPLASZA, to wektor normalny powierzchni.
    Dla scianki pnia ten kierunek wskazuje na zewnatrz od osi, czyli poziomo.

    To jest ta sama cecha, ktora w notebooku z PyG nazywala sie "verticality"
    i byla liczona osobnym skryptem w CloudCompare.

    Liczymy porcjami, bo tablica posrednia ma rozmiar N x k x 3 i dla
    kilku milionow punktow nie zmiescilaby sie w pamieci.
    """
    kd = cKDTree(punkty)
    k = min(k_sasiadow, len(punkty))
    wynik = np.empty(len(punkty))

    porcja = 200_000
    for start in range(0, len(punkty), porcja):
        koniec = min(start + porcja, len(punkty))
        _, sasiedzi = kd.query(punkty[start:koniec], k=k, workers=-1)

        otoczenia = punkty[sasiedzi]
        otoczenia = otoczenia - otoczenia.mean(axis=1, keepdims=True)
        kowariancje = np.einsum('nki,nkj->nij', otoczenia, otoczenia) / k
        _, wektory = np.linalg.eigh(kowariancje)
        wynik[start:koniec] = np.abs(wektory[:, 2, 0])

    return wynik


def filtr_pionowosci_i_ciaglosci(punkty_plastra):
    """
    Z plastra zostawia tylko to, co wyglada jak PIEN.

    To jest krok, ktory decyduje o powodzeniu na prawdziwym, gestym skanie.
    Bez niego DBSCAN w gestym lesie zwraca kilka wielkich kleksow zamiast
    kilkudziesieciu pni.

    DWA FILTRY, JEDEN PO DRUGIM:

    FILTR 1 - PIONOWOSC POWIERZCHNI
        Dla kazdego punktu bierzemy jego najblizszych sasiadow i pytamy:
        "jak ustawiona jest powierzchnia, na ktorej lezy ten punkt?"

        Liczymy to metoda PCA (analiza glownych skladowych). Brzmi groznie,
        ale pomysl jest prosty: chmurka sasiadow ma jakis ksztalt, a PCA
        mowi, w ktorych kierunkach jest rozciagnieta.
          - punkty na scianie pnia: rozciagniete w dwoch kierunkach (wzdluz
            i w gore pnia), plaskie w trzecim - w kierunku OD osi pnia.
            Ten trzeci kierunek to WEKTOR NORMALNY i jest on POZIOMY.
          - punkty na ziemi: normalna skierowana PIONOWO w gore.
          - igliwie i drobne galazki: chmurka bez wyraznego ksztaltu.

        Zostawiamy punkty, ktorych normalna jest bliska poziomej - czyli
        |skladowa_z normalnej| < PIONOWOSC_MAX_NZ.

        To dokladnie ta sama cecha, ktora w notebooku z PyG nazywala sie
        "verticality" i byla liczona zewnetrznym skryptem w CloudCompare.

    FILTR 2 - CIAGLOSC W PIONIE
        Po filtrze 1 zostaja jeszcze pionowe kawalki galezi. Odrozniamy je
        od pni tak: pien ciagnie sie przez CALA wysokosc plastra, galaz nie.
        Dzielimy teren na pionowe slupki i zostawiamy tylko te, w ktorych
        punkty wystepuja na wielu poziomach naraz.
    """
    from scipy.spatial import cKDTree as _KD

    n_wej = len(punkty_plastra)

    # --- FILTR 1: pionowosc ---------------------------------------------
    kd = _KD(punkty_plastra)
    k = min(P.PIONOWOSC_PROMIEN_SASIEDZTWA, n_wej)
    _, sasiedzi = kd.query(punkty_plastra, k=k, workers=-1)

    # Macierz kowariancji sasiedztwa kazdego punktu i jej wektory wlasne.
    # Wektor wlasny o NAJMNIEJSZEJ wartosci wlasnej = kierunek, w ktorym
    # chmurka jest najplaska = wektor normalny powierzchni.
    otoczenia = punkty_plastra[sasiedzi]
    otoczenia = otoczenia - otoczenia.mean(axis=1, keepdims=True)
    kowariancje = np.einsum('nki,nkj->nij', otoczenia, otoczenia) / k
    _, wektory = np.linalg.eigh(kowariancje)
    normalne_z = np.abs(wektory[:, 2, 0])      # skladowa Z wektora normalnego

    pionowe = normalne_z < P.PIONOWOSC_MAX_NZ
    print(f"         filtr pionowosci (|nz|<{P.PIONOWOSC_MAX_NZ}): "
          f"zostaje {int(pionowe.sum()):,} z {n_wej:,} "
          f"({pionowe.mean()*100:.1f}%)")

    kandydaci = punkty_plastra[pionowe]
    if len(kandydaci) == 0:
        return kandydaci

    # --- FILTR 2: ciaglosc pionowa --------------------------------------
    x, y, z = kandydaci[:, 0], kandydaci[:, 1], kandydaci[:, 2]
    kol = ((x - x.min()) / P.CIAGLOSC_KOMORKA_XY).astype(np.int64)
    wie = ((y - y.min()) / P.CIAGLOSC_KOMORKA_XY).astype(np.int64)
    slupek = wie * (kol.max() + 1) + kol
    poziom = ((z - z.min()) / P.CIAGLOSC_KROK_PIONOWY).astype(np.int64)

    # Liczymy, ile ROZNYCH poziomow jest obsadzonych w kazdym slupku.
    pary = np.unique(np.column_stack([slupek, poziom]), axis=0)
    slupki_u, ile_poziomow = np.unique(pary[:, 0], return_counts=True)
    dobre_slupki = slupki_u[ile_poziomow >= P.CIAGLOSC_MIN_POZIOMOW]

    ciagle = np.isin(slupek, dobre_slupki)
    print(f"         filtr ciaglosci (>= {P.CIAGLOSC_MIN_POZIOMOW} poziomow "
          f"po {P.CIAGLOSC_KROK_PIONOWY} m): zostaje "
          f"{int(ciagle.sum()):,} ({ciagle.sum()/n_wej*100:.1f}% wejscia)")

    return kandydaci[ciagle]


def dopasuj_okrag_ransac(x, y, kotwica_x, kotwica_y, rng,
                         max_odchylka=0.08, rmax=0.35):
    """
    DOPASOWANIE OKREGU ODPORNE NA PODSZYT (metoda RANSAC + domiar).

    PO CO, skoro jest juz dopasuj_okrag_odpornie():
        Tamta metoda odsiewa punkty odstajace iteracyjnie i dziala, dopoki
        smieci jest MNIEJ NIZ POLOWA. W podszycie jest ich wiecej, wiec juz
        pierwsze dopasowanie lezy w zlym miejscu i dalsze iteracje tego nie
        naprawiaja. Sprawdzone na prawdziwym skanie: z 22 pni widocznych na
        1.3 m tamta metoda przyjmowala 11, i przy tym myliła sie nawet o 36 cm,
        nie zglaszajac zadnego problemu.

    JAK TO DZIALA - dwa etapy:

      ETAP 1, ZNAJDZ. Losujemy po trzy punkty; przez kazde trzy przechodzi
        dokladnie jeden okrag. Liczymy, ile punktow lezy NA nim (dobrze) i ile
        W jego SRODKU (zle - pien jest w srodku pusty). Najlepszy okrag to ten
        o najwyzszej roznicy. Losowanie powtarzamy kilkaset razy. Taka metoda
        nie przejmuje sie tym, ze wiekszosc punktow to smieci - wystarczy, ze
        raz trafi trzy punkty lezace na pniu.

      ETAP 2, ZMIERZ. Z calego wejscia zostawiamy tylko waski pierscien wokol
        znalezionego okregu i dopiero na nim liczymy dokladne dopasowanie
        najmniejszymi kwadratami. Smieci juz tam nie ma, wiec wynik jest
        precyzyjny.

    KOTWICA (kotwica_x, kotwica_y) to znane polozenie osi pnia. Srodek okregu
    nie moze od niej odbiec dalej niz max_odchylka. To jest kluczowe: bez tego
    ograniczenia RANSAC znajduje wielki okrag przechodzacy przez podszyt, bo
    zbiera na nim wiecej punktow niz na prawdziwym pniu. Na danych testowych
    piersnice wychodzily wtedy o 11-18 cm za grube; przy ograniczeniu do 8 cm
    blad spadl do +2.6 cm.
    """
    n = len(x)
    if n < 12:
        return None

    najlepszy, najlepszy_wynik = None, -1e9
    for _ in range(P.RANSAC_PROBY):
        i, j, k = rng.choice(n, 3, replace=False)
        ax, ay, bx, by, cx_, cy_ = x[i], y[i], x[j], y[j], x[k], y[k]
        mian = 2 * (ax * (by - cy_) + bx * (cy_ - ay) + cx_ * (ay - by))
        if abs(mian) < 1e-9:
            continue      # trzy punkty w jednej linii - okregu nie ma
        ux = ((ax**2 + ay**2) * (by - cy_) + (bx**2 + by**2) * (cy_ - ay)
              + (cx_**2 + cy_**2) * (ay - by)) / mian
        uy = ((ax**2 + ay**2) * (cx_ - bx) + (bx**2 + by**2) * (ax - cx_)
              + (cx_**2 + cy_**2) * (bx - ax)) / mian
        r = np.hypot(ax - ux, ay - uy)

        if not (P.MIN_SREDNICA_PNIA / 2 <= r <= rmax):
            continue
        if np.hypot(ux - kotwica_x, uy - kotwica_y) > max_odchylka:
            continue

        odl = np.hypot(x - ux, y - uy)
        na_okregu = np.abs(odl - r) < P.RANSAC_SZEROKOSC
        w_srodku = odl < 0.7 * r
        wynik = na_okregu.sum() - P.RANSAC_KARA_SRODEK * w_srodku.sum()
        if wynik > najlepszy_wynik:
            najlepszy_wynik, najlepszy = wynik, (ux, uy, r)

    if najlepszy is None:
        return None
    ux, uy, r0 = najlepszy

    odl = np.hypot(x - ux, y - uy)
    pierscien = np.abs(odl - r0) < max(0.25 * r0, 0.04)
    if pierscien.sum() < 10:
        return None

    dok = dopasuj_okrag_odpornie(x[pierscien], y[pierscien])
    if dok is None:
        return None
    cx, cy, r, blad, pokrycie, _, n_uz = dok

    # Pustosc liczymy w OTOCZENIU okregu (do 1.2 promienia), nie na calym
    # wejsciu - inaczej daleki podszyt rozcienczylby miare.
    odl2 = np.hypot(x - cx, y - cy)
    w_poblizu = odl2 < 1.2 * r
    if w_poblizu.sum() == 0:
        return None
    pustosc = float(1.0 - (odl2 < 0.7 * r).sum() / w_poblizu.sum())

    return cx, cy, r, blad, pokrycie, pustosc, int(n_uz)


def nachylenie_srednicy(lancuch):
    """
    O ile centymetrow na metr wysokosci zmienia sie srednica WZDLUZ CALEGO
    lancucha. Dla pnia UJEMNE (zweza sie ku gorze). Dodatnie = to nie pien.
    Patrz dlugi komentarz przy MAX_PRZYROST_SREDNICY_CM_NA_M.
    """
    if len(lancuch) < 6:
        return np.nan            # za krotki lancuch - nachylenie to loteria
    h = np.array([o[1] for o in lancuch], dtype=float)
    srednice = np.array([2 * o[4] for o in lancuch], dtype=float)
    if h.max() - h.min() < 1.0:
        return np.nan            # za maly zakres wysokosci
    return round(float(np.polyfit(h, srednice, 1)[0] * 100), 3)


def policz_sciane(lancuch, kd_pelne, slab_pelny, wys_pelny, n_sektorow=36):
    """
    CZY TEN PIEN JEST SCIANA? Zwraca liczbe od 0 do 1.

    POMYSL: skaner stoi w jednym miejscu, wiec prawdziwy pien widzi ZAWSZE
    OD TEJ SAMEJ STRONY - na kazdej wysokosci swieca te same sektory katowe.
    Kepa podrostow jest inna: okrag powstaje tam PRZYPADKIEM z kilku osobnych
    patykow, a pol metra wyzej stoja juz inne patyki, wiec swieca inne
    sektory.
    Liczymy wiec, jak bardzo zbior zajetych sektorow jest podobny miedzy
    SASIADUJACYMI plastrami (miara Jaccarda), i usredniamy po calym lancuchu.
        1.0 = na kazdej wysokosci swieci dokladnie to samo  -> pien
        0.2 = co plaster co innego                          -> gaszcz

    DLACZEGO TO JEST LEPSZE NIZ PUSTOSC SRODKA: pustosc, jaka pien moze
    osiagnac, zalezy od jego GRUBOSCI (szum skanera jest staly, a promien
    nie), wiec ostry prog pustosci wycina cienkie pnie. Tutaj tego problemu
    nie ma, bo liczymy KTORE strony sa oswietlone, a nie ile jest punktow.
    Zmierzone na sztucznym lesie:
        pnie  7-10 cm: sciana 1.000
        pnie 10-15 cm: sciana 1.000
        pnie 25-45 cm: sciana 0.979 - 0.997
        pnie 45-60 cm: sciana 0.968 - 0.995
    Czyli wynik nie zalezy od grubosci - o to chodzilo.

    Na danych rzeczywistych (poletko S2o, zaslaniajacy podszyt) drzewa
    potwierdzone przez 3DFin mialy 0.741 - 1.000 (mediana 0.917), a reszta
    0.202 - 0.957 (mediana 0.785).
    """
    if kd_pelne is None or len(lancuch) < 3:
        return np.nan

    sektory = []
    for o in lancuch:
        h, cx, cy, r = o[1], o[2], o[3], o[4]
        k = np.asarray(kd_pelne.query_ball_point((cx, cy), r * 1.35),
                       dtype=np.int64)
        if len(k) == 0:
            sektory.append(set())
            continue
        k = k[(wys_pelny[k] >= h - P.SLEDZENIE_KROK / 2) &
              (wys_pelny[k] < h + P.SLEDZENIE_KROK / 2)]
        if len(k) == 0:
            sektory.append(set())
            continue
        dx = slab_pelny[k, 0] - cx
        dy = slab_pelny[k, 1] - cy
        odl = np.hypot(dx, dy)
        na_obwodzie = (odl > r * 0.65) & (odl < r * 1.35)
        if na_obwodzie.sum() < 5:
            sektory.append(set())
            continue
        kat = np.degrees(np.arctan2(dy[na_obwodzie],
                                    dx[na_obwodzie])) % 360
        sektory.append(set((kat // (360 / n_sektorow)).astype(int)))

    podobienstwa = [len(a & b) / len(a | b)
                    for a, b in zip(sektory[:-1], sektory[1:]) if a and b]
    if not podobienstwa:
        return np.nan
    return round(float(np.mean(podobienstwa)), 3)


def krok5b_sledz_pnie(punkty, wysokosc_ng):
    """
    WYKRYWANIE DRZEW PRZEZ SLEDZENIE PNI W GORE.

    Zwraca DataFrame z jednym wierszem na drzewo oraz slownik lancuchow
    (do diagnostyki i do policzenia zbiezystosci).

    TRZY ETAPY:

      ETAP 1 - OKREGI W KAZDYM PLASTRZE
        Kroimy dolne metry lasu na plastry po SLEDZENIE_KROK metra.
        W kazdym plastrze grupujemy punkty (DBSCAN) i do kazdej grupy
        probujemy dopasowac okrag. Zostawiamy tylko te dopasowania, ktore
        wygladaja jak przekroj pnia: sensowny promien, punkty faktycznie
        lezace na okregu i otaczajace go z wielu stron.

      ETAP 2 - LACZENIE OKREGOW W LANCUCHY
        Idziemy od dolu do gory. Kazdy nowy okrag probujemy doczepic do
        istniejacego lancucha - jesli lezy prawie dokladnie nad jego koncem
        i ma podobny promien. Jesli nie pasuje do zadnego, zaczyna nowy
        lancuch.

      ETAP 3 - WYBOR LANCUCHOW, KTORE SA DRZEWAMI
        Lancuch musi miec co najmniej SLEDZENIE_MIN_PLASTROW ogniw.
        Krzak nie da dlugiego lancucha - i o to wlasnie chodzi.

      Na koniec, z calego lancucha wyznaczamy promien na wysokosci 1.3 m
      (dopasowujac prosta promien-od-wysokosci). To DOKLADNIEJSZE niz pomiar
      z jednego plastra, bo korzysta z kilkunastu niezaleznych pomiarow
      i przy okazji daje zbiezystosc pnia.
    """
    print(f"\n[KROK 5] Sledze pnie przez plastry "
          f"{P.SLEDZENIE_DOL}-{P.SLEDZENIE_GORA} m co {P.SLEDZENIE_KROK} m")

    poziomy = np.arange(P.SLEDZENIE_DOL, P.SLEDZENIE_GORA, P.SLEDZENIE_KROK)
    rng = np.random.default_rng(7)

    # =================================================================
    # ETAP 0: zostaw tylko powierzchnie PIONOWE
    # =================================================================
    # Bez tego kroku DBSCAN w gestym lesie sklei pien z przylegajacymi do
    # niego galeziami w jeden klaster. Taki klaster nie jest juz czystym
    # pierscieniem, wiec okrag dopasowuje sie do niego kiepsko i prawdziwy
    # pien wypada przez filtr bledu. (Sprawdzone: bez tego kroku wykrywalnosc
    # spadala kilkukrotnie.)
    #
    # Filtr pionowosci usuwa galezie i igliwie, a scianki pni zostawia -
    # wiec do grupowania trafiaja juz prawie same pnie.
    w_slabie = ((wysokosc_ng >= P.SLEDZENIE_DOL) &
                (wysokosc_ng < P.SLEDZENIE_GORA))
    slab = punkty[w_slabie]
    wys_slab = wysokosc_ng[w_slabie]

    # -----------------------------------------------------------------
    # DWA ZBIORY PUNKTOW, I TO JEST WAZNE
    # -----------------------------------------------------------------
    # slab      - PRZERZEDZONY. Sluzy do GRUPOWANIA (DBSCAN). Przerzedzenie
    #             jest tu konieczne, bo inaczej program zjada pamiec.
    # slab_pelny- PELNA ROZDZIELCZOSC. Sluzy do DOPASOWANIA OKREGU i do
    #             liczenia pustosci srodka.
    #
    # DLACZEGO OSOBNO - to byl prawdziwy blad, nie kosmetyka:
    #   Przerzedzenie do 3 cm przesuwa kazdy punkt nawet o 1.5 cm. Dla pnia
    #   o srednicy 50 cm (promien 25 cm) to nic. Dla pnia o srednicy 7 cm
    #   (promien 3.5 cm) to 43% promienia - przekroj przestaje byc
    #   pierscieniem i robi sie z niego plama.
    #   Zmierzone na idealnym, bezbledym cylindrze:
    #       przerzedzenie 3 cm : pien 7 cm ma pustosc 0.73, krzak 0.67
    #                            -> NIEROZROZNIALNE, i pien leci przez prog 0.80
    #       bez przerzedzenia  : pien 7 cm ma pustosc 0.91, krzak 0.51
    #                            -> rozdzielone wzorowo
    #   Czyli kryterium pustosci bylo dobre, tylko liczone na zepsutych
    #   danych. Dlatego grupujemy na przerzedzonych, a mierzymy na pelnych.
    #
    # Zeby na pelnych punktach nie wrocily galezie usuniete filtrem
    # pionowosci, przenosimy decyzje filtru z voxela na wszystkie punkty,
    # ktore w tym voxelu siedzialy (sluzy do tego tablica "gdzie_voxel").
    slab_pelny, wys_pelny = slab, wys_slab

    if P.SLEDZENIE_VOXEL and P.SLEDZENIE_VOXEL > 0:
        kl = np.floor(slab / P.SLEDZENIE_VOXEL).astype(np.int64)
        _, pierw, gdzie_voxel = np.unique(kl, axis=0, return_index=True,
                                          return_inverse=True)
        gdzie_voxel = gdzie_voxel.ravel()
        slab, wys_slab = slab[pierw], wys_slab[pierw]
    else:
        gdzie_voxel = np.arange(len(slab))

    print(f"         slab {P.SLEDZENIE_DOL}-{P.SLEDZENIE_GORA} m: "
          f"{len(slab_pelny):,} pkt, do grupowania przerzedzone do "
          f"{P.SLEDZENIE_VOXEL} m -> {len(slab):,} pkt")

    if P.UZYJ_FILTRU_PIONOWOSCI and len(slab) > P.PIONOWOSC_PROMIEN_SASIEDZTWA:
        nz = oblicz_pionowosc(slab, P.PIONOWOSC_PROMIEN_SASIEDZTWA)
        pionowe = nz < P.PIONOWOSC_MAX_NZ
        print(f"         filtr pionowosci (|nz|<{P.PIONOWOSC_MAX_NZ}): "
              f"zostaje {int(pionowe.sum()):,} ({pionowe.mean()*100:.1f}%)")
        zostaw_pelne = pionowe[gdzie_voxel]
        slab, wys_slab = slab[pionowe], wys_slab[pionowe]
        slab_pelny, wys_pelny = slab_pelny[zostaw_pelne], wys_pelny[zostaw_pelne]

    # =================================================================
    # ETAP 1: okregi w kazdym plastrze
    # =================================================================
    # jeden okrag = (nr_poziomu, wysokosc, srodek_x, srodek_y, promien,
    #                blad_dopasowania, pokrycie_katowe, pustosc, liczba_punktow)
    okregi = []

    for i_poz, h in enumerate(poziomy):
        w_plastrze = (wys_slab >= h) & (wys_slab < h + P.SLEDZENIE_KROK)
        if w_plastrze.sum() < P.SLEDZENIE_DBSCAN_MIN:
            continue

        pkt = slab[w_plastrze][:, :2]

        # Te same punkty, ale w pelnej rozdzielczosci - na nich bedziemy
        # dopasowywac okregi (patrz komentarz przy slab_pelny).
        w_plastrze_pelne = ((wys_pelny >= h) &
                            (wys_pelny < h + P.SLEDZENIE_KROK))
        pkt_pelne = slab_pelny[w_plastrze_pelne][:, :2]
        drzewo_pelne = cKDTree(pkt_pelne) if len(pkt_pelne) else None

        etykiety = DBSCAN(eps=P.SLEDZENIE_DBSCAN_EPS,
                          min_samples=P.SLEDZENIE_DBSCAN_MIN,
                          n_jobs=-1).fit_predict(pkt)

        for nr in set(etykiety) - {-1}:
            grupa = pkt[etykiety == nr]

            rozp_x = grupa[:, 0].max() - grupa[:, 0].min()
            rozp_y = grupa[:, 1].max() - grupa[:, 1].min()
            szerszy = max(rozp_x, rozp_y)
            if not (P.MIN_SREDNICA_PNIA <= szerszy <= P.MAX_SREDNICA_PNIA):
                continue

            # Podmieniamy przerzedzone punkty klastra na wszystkie punkty
            # lezace w tym samym miejscu. Promien brany z zapasem jednego
            # voxela, zeby nie obciac scianki pnia.
            grupa_do_pomiaru = grupa
            if drzewo_pelne is not None:
                srodek_zgrubny = grupa.mean(axis=0)
                zasieg = szerszy / 2 + max(P.SLEDZENIE_VOXEL, 0.01) * 1.5
                blisko = drzewo_pelne.query_ball_point(srodek_zgrubny, zasieg)
                if len(blisko) >= P.SLEDZENIE_DBSCAN_MIN:
                    grupa_do_pomiaru = pkt_pelne[blisko]

            dop = dopasuj_okrag_odpornie(grupa_do_pomiaru[:, 0],
                                         grupa_do_pomiaru[:, 1])
            if dop is None:
                continue
            cx, cy, r, blad, pokrycie, pustosc, n_uz = dop

            if not (P.MIN_SREDNICA_PNIA / 2 <= r <= P.MAX_SREDNICA_PNIA / 2):
                continue
            # progi WYKRYWANIA - luzne; ostre przyjda w etapie 2.5
            if blad > P.DETEKCJA_MAX_BLAD:
                continue
            if pokrycie < P.DETEKCJA_MIN_POKRYCIE_KATOWE:
                continue
            if pustosc < P.DETEKCJA_MIN_PUSTOSC:
                continue      # wypelnione w srodku -> krzak, nie pien

            okregi.append((i_poz, float(h + P.SLEDZENIE_KROK / 2),
                           cx, cy, r, blad, pokrycie, pustosc, n_uz))

    print(f"         znalezionych okregow we wszystkich plastrach: {len(okregi)}")
    if not okregi:
        return pd.DataFrame(), []

    # =================================================================
    # ETAP 2: laczenie w lancuchy
    # =================================================================
    okregi.sort(key=lambda o: o[0])                 # od dolu do gory
    lancuchy = []                                   # lista list okregow

    for o in okregi:
        i_poz, h, cx, cy, r = o[0], o[1], o[2], o[3], o[4]

        najlepszy, najlepsza_odl = None, np.inf
        for lan in lancuchy:
            ost = lan[-1]
            przerwa = i_poz - ost[0]
            if przerwa < 1 or przerwa > 1 + P.SLEDZENIE_MAX_PRZERWA:
                continue                            # za blisko albo za daleko

            odl = np.hypot(cx - ost[2], cy - ost[3])
            # dopuszczalne przesuniecie rosnie z wielkoscia przerwy
            if odl > P.SLEDZENIE_MAX_PRZESUNIECIE * przerwa:
                continue
            if abs(r - ost[4]) / max(ost[4], 1e-6) > P.SLEDZENIE_MAX_ZMIANA_PROMIENIA:
                continue

            if odl < najlepsza_odl:
                najlepszy, najlepsza_odl = lan, odl

        if najlepszy is not None:
            najlepszy.append(o)
        else:
            lancuchy.append([o])

    dlugosci = sorted((len(l) for l in lancuchy), reverse=True)
    print(f"         lancuchow: {len(lancuchy)} "
          f"(najdluzsze: {dlugosci[:8]})")

    # =================================================================
    # ETAP 2.5: POWTORNY POMIAR WZGLEDEM OSI PNIA
    # =================================================================
    # Pierwszy przebieg mial znalezc, GDZIE stoja pnie - i to zrobil.
    # Ale kazdy okrag byl tam dopasowywany osobno, bez wiedzy o pozostalych,
    # wiec przy niepelnym luku srodek potrafi odskoczyc o kilkanascie cm.
    #
    # Teraz, gdy lancuch juz istnieje, znamy OS pnia - prosta przechodzaca
    # przez srodki wszystkich jego okregow. Wracamy wiec do danych i mierzymy
    # kazdy plaster jeszcze raz, tym razem wymagajac, zeby srodek okregu lezal
    # blisko tej osi. To samo robi 3DFin (parametr distance_to_axis).
    #
    # Zysk na danych testowych: piersnica z +12 cm bledu do +2.6 cm.
    print(f"         powtorny pomiar wzgledem osi pnia...")
    poprawione = 0
    # Ten pomiar JEST pomiarem (a nie wykrywaniem), wiec idzie na punktach w
    # pelnej rozdzielczosci. Drzewo kd zbudowane raz, bo inaczej przeszukanie
    # calej chmury dla kazdego plastra kazdego lancucha trwa wieki.
    kd_pelne = cKDTree(slab_pelny[:, :2]) if len(slab_pelny) else None
    for lan in lancuchy:
        if len(lan) < P.SLEDZENIE_MIN_PLASTROW:
            continue
        tab = np.array([[o[1], o[2], o[3]] for o in lan])
        h_l, cx_l, cy_l = tab[:, 0], tab[:, 1], tab[:, 2]
        if len(h_l) >= 3:
            wx = np.polyfit(h_l, cx_l, 1)
            wy = np.polyfit(h_l, cy_l, 1)
        else:
            wx = np.array([0.0, float(cx_l.mean())])
            wy = np.array([0.0, float(cy_l.mean())])

        for idx in range(len(lan)):
            o = lan[idx]
            h_tu = o[1]
            kx = float(np.polyval(wx, h_tu))
            ky = float(np.polyval(wy, h_tu))

            if kd_pelne is None:
                continue
            w_kole = np.asarray(kd_pelne.query_ball_point((kx, ky), 0.6),
                                dtype=np.int64)
            if len(w_kole) < 12:
                continue
            w_kole = w_kole[
                (wys_pelny[w_kole] >= h_tu - P.SLEDZENIE_KROK / 2) &
                (wys_pelny[w_kole] < h_tu + P.SLEDZENIE_KROK / 2)]
            if len(w_kole) < 12:
                continue

            nowy = dopasuj_okrag_ransac(slab_pelny[w_kole, 0],
                                        slab_pelny[w_kole, 1], kx, ky,
                                        rng, P.RANSAC_MAX_ODCHYLKA_OSI)
            if nowy is None:
                continue
            ncx, ncy, nr, nbl, npk, npu, nnu = nowy
            if nbl > P.DBH_MAX_BLAD_DOPASOWANIA or npu < P.DBH_MIN_PUSTOSC:
                continue
            lan[idx] = (o[0], o[1], ncx, ncy, nr, nbl, npk, npu, nnu)
            poprawione += 1
    print(f"         przemierzono okregow: {poprawione}")

    # =================================================================
    # ETAP 2.7: DOCIAGANIE LANCUCHA W DOL, do wysokosci piersnicy
    # =================================================================
    # PO CO TO JEST
    #   Zmierzone na 9F: drzewo 82 mialo 14 okregow od 2.62 do 5.87 m,
    #   kazdy z pokryciem 360 st., bledem 1 cm i pustoscia 0.997 - idealny
    #   walec - i PUSTA piersnice. Ponizej 2.6 m DBSCAN sklejal pien
    #   z podszytem stojacym tuz obok (eps = 15 cm), wiec "klaster pnia"
    #   mial 48-80 cm rozpietosci, okrag na nim nie trzymal sie kupy
    #   i plaster wypadal. Lancuch sie urywal, choc pien byl widoczny
    #   dookola.
    #
    # NA CZYM POLEGA ROZWIAZANIE
    #   Szukanie na slepo w podszycie nie dziala. Ale gdy mamy juz lancuch
    #   WYZEJ, to wiemy dwie rzeczy, ktorych szukanie na slepo nie ma:
    #   GDZIE jest os pnia i JAKI ma miec promien. Schodzimy wiec plaster
    #   po plastrze w dol i za kazdym razem:
    #     - kotwiczymy srodek na osi przedluzonej z lancucha,
    #     - bierzemy TYLKO punkty z waskiego pierscienia wokol
    #       spodziewanego promienia (podszyt obok pnia tam nie wchodzi),
    #     - mierzymy tym samym RANSAC-iem co w etapie 2.5.
    #
    # DLACZEGO TO NIE DORYSOWUJE PNI, KTORYCH NIE MA
    #   Pierscien musi byc NAPRAWDE wypelniony punktami, a promien nie moze
    #   odbiec od spodziewanego o wiecej niz DOCIAGANIE_MAX_ROZNICA_R.
    #   Zmierzone na 9F: drzewo 74 zatrzymalo sie natychmiast, bo pierscien
    #   dal 8.1 cm zamiast spodziewanych 28.0 - i dobrze, bo ponizej 2.1 m
    #   ten pien jest splatany z sasiadem.
    #
    # PROG POKRYCIA JEST TU LUZNIEJSZY NIZ PRZY WYKRYWANIU - celowo.
    #   Luk 120 stopni jest bezuzyteczny, gdy srodek okregu jest nieznany
    #   (przez krotki luk przechodzi nieskonczenie wiele okregow o roznych
    #   promieniach). Gdy srodek jest PRZYBITY osia kilkunastu okregow
    #   powyzej, ten sam luk 120 stopni wyznacza promien jednoznacznie.
    #
    # KROK JEST SCISLE DOKLADAJACY: uruchamiamy go tylko dla lancuchow,
    #   ktore NIE siegaja juz piersnicy. Drzewa, ktore maja piersnice
    #   zmierzona, nie sa ruszane - zadna dzialajaca liczba nie moze sie
    #   przez to zmienic.
    if P.DOCIAGAJ_LANCUCH_W_DOL and kd_pelne is not None:
        dociagniete, dolozonych = 0, 0
        for lan in lancuchy:
            if len(lan) < P.SLEDZENIE_MIN_PLASTROW:
                continue
            h_min = min(o[1] for o in lan)
            if h_min <= 1.3 + P.DBH_TOLERANCJA_WYSOKOSCI:
                continue            # juz siega piersnicy - nie dotykamy

            dodane_tu = 0
            while True:
                h_min = min(o[1] for o in lan)
                h_cel = h_min - P.SLEDZENIE_KROK
                if h_cel < P.DOCIAGANIE_DOL:
                    break

                # os i promien przedluzone z DOLNEJ czesci lancucha
                tab = np.array([[o[1], o[2], o[3], o[4]] for o in lan])
                blisko_spodu = tab[:, 0] <= h_min + P.DOCIAGANIE_OKNO
                if blisko_spodu.sum() < 3:
                    blisko_spodu = np.ones(len(tab), bool)
                hs = tab[blisko_spodu, 0]
                ox = float(np.polyval(np.polyfit(hs, tab[blisko_spodu, 1], 1), h_cel))
                oy = float(np.polyval(np.polyfit(hs, tab[blisko_spodu, 2], 1), h_cel))
                orr = float(np.polyval(np.polyfit(hs, tab[blisko_spodu, 3], 1), h_cel))
                if not (P.MIN_SREDNICA_PNIA / 2 <= orr <= P.MAX_SREDNICA_PNIA / 2):
                    break

                # punkty plastra w pelnej rozdzielczosci, w pierscieniu
                w_kole = kd_pelne.query_ball_point(
                    (ox, oy), orr + P.DOCIAGANIE_PIERSCIEN)
                if len(w_kole) < 12:
                    break
                w_kole = np.asarray(w_kole)
                tu = w_kole[(wys_pelny[w_kole] >= h_cel - P.SLEDZENIE_KROK / 2) &
                            (wys_pelny[w_kole] < h_cel + P.SLEDZENIE_KROK / 2)]
                if len(tu) < 12:
                    break
                g = slab_pelny[tu][:, :2]
                d_od_osi = np.hypot(g[:, 0] - ox, g[:, 1] - oy)
                w_pierscieniu = g[d_od_osi > max(0.02, orr - P.DOCIAGANIE_PIERSCIEN)]
                if len(w_pierscieniu) < 12:
                    break

                dop = dopasuj_okrag_ransac(
                    w_pierscieniu[:, 0], w_pierscieniu[:, 1], ox, oy, rng,
                    max_odchylka=P.DOCIAGANIE_MAX_ODCHYLKA_OSI,
                    rmax=P.MAX_SREDNICA_PNIA / 2)
                if dop is None:
                    break
                ncx, ncy, nr, nbl, npk, npu, nnu = dop
                if (nbl > P.DOCIAGANIE_MAX_BLAD or
                        npk < P.DOCIAGANIE_MIN_POKRYCIE or
                        npu < P.DOCIAGANIE_MIN_PUSTOSC or
                        abs(nr - orr) > P.DOCIAGANIE_MAX_ROZNICA_R):
                    break

                lan.insert(0, (lan[0][0] - 1, h_cel, ncx, ncy, nr,
                               nbl, npk, npu, nnu))
                dodane_tu += 1
                if dodane_tu >= P.DOCIAGANIE_MAX_PLASTROW:
                    break

            if dodane_tu:
                dociagniete += 1
                dolozonych += dodane_tu
        print(f"         dociagnietych lancuchow w dol: {dociagniete} "
              f"(+{dolozonych} okregow)")

    # =================================================================
    # ETAP 3: ktore lancuchy to drzewa
    # =================================================================
    drzewa, zachowane = [], []
    for lan in lancuchy:
        if len(lan) < P.SLEDZENIE_MIN_PLASTROW:
            continue

        tab = np.array([[o[1], o[2], o[3], o[4]] for o in lan])  # h,cx,cy,r
        h, cx, cy, r = tab[:, 0], tab[:, 1], tab[:, 2], tab[:, 3]

        # --- promien na 1.3 m z calego lancucha --------------------------
        # Dopasowujemy prosta promien(wysokosc) i odczytujemy ja na 1.3 m.
        # Nachylenie tej prostej to ZBIEZYSTOSC pnia (ile cm promienia ubywa
        # na metr wysokosci) - przydatna sama w sobie.
        # Uzywamy tylko ogniw z zakresu 0.8-3.5 m: nizej sa nabiegi
        # korzeniowe, wyzej zaczynaja sie galezie.
        # --- CZY LANCUCH W OGOLE SIEGA WYSOKOSCI PIERSNICY? -------------
        # Jesli najnizszy zmierzony okrag jest na 2.5 m, to promien na 1.3 m
        # nie jest POMIAREM, tylko przedluzeniem prostej w dol - czyli
        # zgadywaniem. Na podgladzie widac to jako okrag narysowany w miejscu,
        # gdzie nie ma ani jednego punktu.
        # Takie drzewo zostaje w tabeli (bo pien istnieje i wysokosc da sie
        # zmierzyc), ale piersnice oznaczamy jako ekstrapolowana.
        odleglosc_do_13 = float(np.min(np.abs(h - 1.3)))
        tol = P.DBH_TOLERANCJA_WYSOKOSCI
        obejmuje_13 = (h.min() <= 1.3 + tol) and (h.max() >= 1.3 - tol)

        # Srednica NAPRAWDE ZMIERZONA - na najnizszej wysokosci, na ktorej
        # udalo sie dopasowac okrag. Gdy podszyt zaslania 1.3 m, to jest
        # jedyna uczciwa liczba, jaka mamy o grubosci tego pnia.
        najnizszy = int(np.argmin(h))
        srednica_zmierzona = float(2 * r[najnizszy])
        wysokosc_pomiaru = float(h[najnizszy])

        # Czy wolno przedluzyc pomiar w dol do 1.3 m? Patrz komentarz przy
        # DBH_MAX_EKSTRAPOLACJA.
        mozna_szacowac = (odleglosc_do_13 <= P.DBH_MAX_EKSTRAPOLACJA and
                          len(lan) >= P.DBH_MIN_OKREGOW_DO_EKSTRAPOLACJI)

        uzyte = (h >= 0.8) & (h <= 3.5)
        if uzyte.sum() >= 3:
            wsp = np.polyfit(h[uzyte], r[uzyte], 1)
            promien_13 = float(np.polyval(wsp, 1.3))
            zbieznosc = float(-wsp[0])
            zrodlo = f"prosta z {int(uzyte.sum())} plastrow"
        else:
            blisko13 = np.argmin(np.abs(h - 1.3))
            promien_13 = float(r[blisko13])
            zbieznosc = np.nan
            zrodlo = "najblizszy plaster"

        if not (P.MIN_SREDNICA_PNIA / 2 <= promien_13 <= P.MAX_SREDNICA_PNIA / 2):
            continue

        # pozycja osi pnia na 1.3 m - tez z dopasowania prostej
        if uzyte.sum() >= 3:
            wsp_x = np.polyfit(h[uzyte], cx[uzyte], 1)
            wsp_y = np.polyfit(h[uzyte], cy[uzyte], 1)
            x13 = float(np.polyval(wsp_x, 1.3))
            y13 = float(np.polyval(wsp_y, 1.3))
            # nachylenie osi: o ile metrow pien ucieka w bok na metr wysokosci
            spadek_x, spadek_y = float(wsp_x[0]), float(wsp_y[0])
        else:
            x13, y13 = float(cx[np.argmin(np.abs(h - 1.3))]), \
                       float(cy[np.argmin(np.abs(h - 1.3))])
            spadek_x = spadek_y = 0.0

        # --- NACHYLENIE PNIA I KOREKTA SREDNICY --------------------------
        # Tniemy pien plaszczyzna POZIOMA. Gdy pien stoi pionowo, przekroj
        # jest kolem. Gdy jest pochylony o kat alfa, przekroj to ELIPSA -
        # dluzsza od prawdziwej srednicy w kierunku pochylenia.
        #
        # Dopasowany okrag wypada mniej wiecej posrodku miedzy krotsza
        # a dluzsza osia elipsy, czyli zawyza. Mnoznik, ktory to cofa:
        #       2*cos(alfa) / (1 + cos(alfa))
        # Dla 0 stopni daje 1.000 (nic nie zmienia), dla 20 st. 0.969
        # (-3%), dla 30 st. 0.928 (-7%).
        #
        # To jest PRZYBLIZENIE - przy niepelnym luku zalezy jeszcze od tego,
        # z ktorej strony skaner widzial pien. Dlatego stosuje je dopiero
        # powyzej 5 stopni (nizej roznica i tak ginie w szumie), a wielkosc
        # poprawki trafia do osobnej kolumny, zebys widzial, co sie stalo.
        nachylenie_rad = float(np.arctan(np.hypot(spadek_x, spadek_y)))
        nachylenie_deg = float(np.degrees(nachylenie_rad))

        if P.KORYGUJ_NACHYLENIE and nachylenie_deg > 5.0:
            c = np.cos(nachylenie_rad)
            mnoznik = 2 * c / (1 + c)
        else:
            mnoznik = 1.0

        promien_13 *= mnoznik
        srednica_zmierzona *= mnoznik

        # ZASADA: piersnica to POMIAR NA 1.3 m. Jesli lancuch tam nie siega,
        # nie wpisujemy niczego do dbh_m.
        #
        # Wczesniejsza wersja przedluzala prosta w dol i wypisywala wynik tak,
        # jakby byl zmierzony. Na danych uzytkownika z 15 takich drzew czesc
        # wyszla sensownie, a czesc chybila o pol metra i okrag ladowal
        # w powietrzu - w podgladzie widac bylo pusty kwadracik z czerwonym
        # kolkiem. Lepiej zostawic puste pole niz liczbe nie do obrony.
        #
        # To, co naprawde zmierzylismy, idzie do osobnych kolumn:
        #   srednica_zmierzona_m + wysokosc_pomiaru_m
        # a przedluzenie prostej - do dbh_szacowany_m, z jawna nazwa.
        drzewa.append({
            "x": x13,
            "y": y13,
            "dbh_m": round(2 * promien_13, 4) if obejmuje_13 else np.nan,
            "dbh_szacowany_m": (np.nan if obejmuje_13 or not mozna_szacowac
                                else round(2 * promien_13, 4)),
            "dbh_do_uzycia_m": (round(2 * promien_13, 4)
                                if (obejmuje_13 or mozna_szacowac) else np.nan),
            "dbh_zrodlo_wartosci": ("pomiar" if obejmuje_13 else
                                    "oszacowanie_ze_zbieznosci"
                                    if mozna_szacowac else "brak"),
            "srednica_zmierzona_m": round(srednica_zmierzona, 4),
            "wysokosc_pomiaru_m": round(wysokosc_pomiaru, 2),
            "liczba_plastrow": len(lan),
            "zakres_pnia_m": round(float(h.max() - h.min()), 2),
            "zbieznosc_m_na_m": round(zbieznosc, 5) if np.isfinite(zbieznosc) else np.nan,
            "nachylenie_pnia_deg": round(nachylenie_deg, 1),
            "korekta_nachylenia_proc": round((mnoznik - 1) * 100, 2),
            "os_spadek_x": round(spadek_x, 5),
            "os_spadek_y": round(spadek_y, 5),
            "sredni_blad_okregu_m": round(float(np.mean([o[5] for o in lan])), 4),
            "srednie_pokrycie_deg": round(float(np.mean([o[6] for o in lan])), 1),
            "srednia_pustosc": round(float(np.mean([o[7] for o in lan])), 3),
            "sciana_pnia": policz_sciane(lan, kd_pelne, slab_pelny, wys_pelny),
            "nachylenie_srednicy_cm_na_m": nachylenie_srednicy(lan),
            "dbh_zrodlo": zrodlo,
            "dbh_ekstrapolowany": not obejmuje_13,
            "odleglosc_pomiaru_od_13m": round(odleglosc_do_13, 2),
        })
        zachowane.append(lan)

    print(f"         lancuchow dluzszych niz {P.SLEDZENIE_MIN_PLASTROW} "
          f"plastrow: {len(drzewa)}")

    # --- SCALANIE DUPLIKATOW ---------------------------------------------
    # Zaslonienie potrafi rozbic jeden pien na kilka lancuchow. Jesli ich osie
    # na 1.3 m leza blisko siebie, to jest jedno drzewo - zostawiamy lancuch
    # najdluzszy, bo jest najlepiej udokumentowany.
    if drzewa and P.SLEDZENIE_MIN_ODLEGLOSC_DRZEW > 0:
        kolejnosc = sorted(range(len(drzewa)),
                           key=lambda i: -drzewa[i]["liczba_plastrow"])
        zostaw, pozycje_ok = [], []
        for i in kolejnosc:
            d = drzewa[i]
            if any(np.hypot(d["x"] - px, d["y"] - py)
                   < P.SLEDZENIE_MIN_ODLEGLOSC_DRZEW for px, py in pozycje_ok):
                continue
            zostaw.append(i)
            pozycje_ok.append((d["x"], d["y"]))
        if len(zostaw) < len(drzewa):
            print(f"         scalono duplikaty: {len(drzewa)} -> {len(zostaw)}")
        zostaw.sort()
        drzewa = [drzewa[i] for i in zostaw]
        zachowane = [zachowane[i] for i in zostaw]

    # --- prog raportowania piersnicy -------------------------------------
    # Patrz komentarz przy MIN_DBH_RAPORTOWANIA. Odrzucamy tylko te drzewa,
    # dla ktorych piersnice ZNAMY i jest mniejsza od progu.
    if drzewa and P.MIN_DBH_RAPORTOWANIA > 0:
        zostaw = [i for i, d in enumerate(drzewa)
                  if d.get("dbh_do_uzycia_m") is None
                  or not np.isfinite(d.get("dbh_do_uzycia_m"))
                  or d["dbh_do_uzycia_m"] >= P.MIN_DBH_RAPORTOWANIA]
        if len(zostaw) < len(drzewa):
            print(f"         prog {P.MIN_DBH_RAPORTOWANIA*100:.0f} cm "
                  f"piersnicy: odrzucono {len(drzewa) - len(zostaw)} "
                  f"za cienkich")
        drzewa = [drzewa[i] for i in zostaw]
        zachowane = [zachowane[i] for i in zostaw]

    print(f"         >>> WYKRYTO DRZEW: {len(drzewa)}")

    return pd.DataFrame(drzewa), zachowane


def krok5_wykryj_pnie(punkty, wysokosc_ng):
    """
    Znajduje pozycje (X, Y) wszystkich pni na poletku.

    POMYSL:
        Wytnij poziomy plaster chmury na wysokosci ok. 1-2 m nad gruntem.
        Patrzac na niego z gory widzisz kilkanascie malych kolek - to przekroje
        pni. Nic innego tam nie ma: runo jest nizej, korony wyzej.
        Wystarczy te kolka policzyc.

    JAK:
        DBSCAN to algorytm grupowania. Dziala tak: "punkty blizej siebie niz
        PROMIEN naleza do tej samej grupy; grupa musi miec co najmniej
        MIN_PUNKTOW punktow, inaczej to szum". Nie trzeba mu z gory mowic,
        ile grup ma znalezc - sam to wykrywa. Dlatego idealnie pasuje tutaj:
        nie wiemy z gory, ile drzew rosnie na poletku.

        Grupujemy TYLKO w poziomie (X, Y), ignorujac Z - dlatego caly pien
        w calym plastrze wpada do jednej grupy.
    """
    print(f"\n[KROK 5] Wykrywam pnie w plastrze "
          f"{P.WARSTWA_PNI_DOL}-{P.WARSTWA_PNI_GORA} m nad gruntem")

    w_plastrze = (wysokosc_ng >= P.WARSTWA_PNI_DOL) & (wysokosc_ng <= P.WARSTWA_PNI_GORA)
    punkty_plastra = punkty[w_plastrze]
    print(f"         punktow w plastrze: {len(punkty_plastra):,}")

    if len(punkty_plastra) < P.DBSCAN_MIN_PUNKTOW:
        raise RuntimeError("Plaster jest prawie pusty - sprawdz WARSTWA_PNI_DOL/GORA.")

    if P.UZYJ_FILTRU_PIONOWOSCI:
        punkty_plastra = filtr_pionowosci_i_ciaglosci(punkty_plastra)
        if len(punkty_plastra) < P.DBSCAN_MIN_PUNKTOW:
            raise RuntimeError(
                "Po filtrze pionowosci nie zostalo nic. Poluzuj PIONOWOSC_MAX_NZ "
                "albo CIAGLOSC_MIN_POZIOMOW, albo wylacz UZYJ_FILTRU_PIONOWOSCI.")

    # Przerzedzenie przed grupowaniem - patrz komentarz przy DBSCAN_VOXEL.
    if P.DBSCAN_VOXEL and P.DBSCAN_VOXEL > 0:
        klucze = np.floor(punkty_plastra / P.DBSCAN_VOXEL).astype(np.int64)
        _, pierwszy = np.unique(klucze, axis=0, return_index=True)
        przed = len(punkty_plastra)
        punkty_plastra = punkty_plastra[pierwszy]
        print(f"         przerzedzenie przed DBSCAN (voxel {P.DBSCAN_VOXEL} m): "
              f"{przed:,} -> {len(punkty_plastra):,}")

    plaster = punkty_plastra[:, :2]          # do grupowania bierzemy tylko X, Y

    etykiety = DBSCAN(eps=P.DBSCAN_PROMIEN,
                      min_samples=P.DBSCAN_MIN_PUNKTOW,
                      n_jobs=-1).fit_predict(plaster)

    # etykieta -1 = DBSCAN uznal te punkty za szum
    numery_grup = sorted(set(etykiety) - {-1})
    print(f"         DBSCAN znalazl grup: {len(numery_grup)}")

    pnie = []
    odrzucone_powod = {"za_male": 0, "za_duze": 0, "wydluzone": 0}

    for nr in numery_grup:
        grupa = plaster[etykiety == nr]

        rozpietosc_x = grupa[:, 0].max() - grupa[:, 0].min()
        rozpietosc_y = grupa[:, 1].max() - grupa[:, 1].min()
        szerszy = max(rozpietosc_x, rozpietosc_y)
        wezszy = max(min(rozpietosc_x, rozpietosc_y), 1e-6)

        # --- filtry zdrowego rozsadku ---
        if szerszy < P.MIN_SREDNICA_PNIA:
            odrzucone_powod["za_male"] += 1
            continue
        if szerszy > P.MAX_SREDNICA_PNIA:
            odrzucone_powod["za_duze"] += 1
            continue
        if szerszy / wezszy > P.MAX_WYDLUZENIE_PNIA:
            # przekroj pnia jest kolisty, a nie wydluzony jak patyk
            odrzucone_powod["wydluzone"] += 1
            continue

        pnie.append({
            "x": float(grupa[:, 0].mean()),
            "y": float(grupa[:, 1].mean()),
            "liczba_punktow_plastra": int(len(grupa)),
        })

    print(f"         odrzucone: za male {odrzucone_powod['za_male']}, "
          f"za duze {odrzucone_powod['za_duze']}, "
          f"wydluzone {odrzucone_powod['wydluzone']}")
    print(f"         >>> WYKRYTO DRZEW: {len(pnie)}")

    return pd.DataFrame(pnie)


# ======================================================================
# KROK 6: SEGMENTACJA
# ======================================================================
def krok6_przypisz_punkty(punkty, pnie_df):
    """
    Przypisuje KAZDY punkt chmury do najblizszego drzewa.

    METODA: "najblizszy pien w poziomie" (diagramy Woronoja w rzucie z gory).
        Dla kazdego punktu patrzymy, ktory pien jest najblizej w plaszczyznie
        XY - i do tego drzewa punkt nalezy. Jakby kazde drzewo mialo wokol
        siebie pionowy slup, a granice slupow przebiegaly w polowie odleglosci
        miedzy pniami.

    OGRANICZENIE - musisz o tym wiedziec:
        Ta metoda tnie korony pionowo. Jesli galaz drzewa A przewiesza sie nad
        pniem drzewa B, jej punkty zostana przypisane do B. Dla DBH i wysokosci
        najczesciej nie ma to znaczenia (pien jest zawsze blisko siebie, a czubek
        zwykle nad wlasnym pniem). Ale jesli bedziesz liczyl objetosc korony
        albo biomase, trzeba czegos madrzejszego - patrz komentarz na koncu pliku.

    Zwraca tablice numerow drzew: 0 = nieprzypisany, 1..N = numer drzewa.
    """
    print(f"\n[KROK 6] Przypisuje punkty do drzew")

    if len(pnie_df) == 0:
        return np.zeros(len(punkty), dtype=np.int32)

    pozycje_pni = pnie_df[["x", "y"]].to_numpy()
    kd = cKDTree(pozycje_pni)
    odlegosc, najblizszy = kd.query(punkty[:, :2], workers=-1)

    id_drzewa = (najblizszy + 1).astype(np.int32)        # numerujemy od 1
    id_drzewa[odlegosc > P.MAX_ODLEGLOSC_OD_PNIA] = 0    # za daleko = niczyj

    nieprzypisane = (id_drzewa == 0).sum()
    print(f"         przypisano: {(id_drzewa > 0).sum():,} punktow")
    print(f"         nieprzypisane (dalej niz {P.MAX_ODLEGLOSC_OD_PNIA} m): "
          f"{nieprzypisane:,}")

    return id_drzewa


def krok6b_przypisz_punkty_grafowo(punkty, wysokosc_ng, pnie_df):
    """
    SEGMENTACJA METODA NAJKROTSZEJ SCIEZKI PRZEZ CHMURE (metoda "graf").

    DLACZEGO PROSTA METODA ZAWODZI:
        Krok 6 pyta "ktory pien jest najblizej W LINII PROSTEJ". Ale gałąź
        wysokiego swierka moze przewieszac sie 15 m nad ziemia dokladnie nad
        pniem malej brzozy. W linii prostej jest blizej brzozy - wiec zostanie
        jej przypisana. Brzoza "urosnie" do 20 m i wysokosc bedzie bzdurna.
        Dotyka to zwlaszcza drzew przyglusonych, rosnacych pod okapem.

    POMYSL TEJ METODY:
        Nie pytaj "co jest najblizej w linii prostej", tylko:
        "gdybym byl wiewiorka i musial zejsc po drewnie do najblizszego pnia,
         DO KTOREGO PNIA bym doszedl najkrotsza droga?"

        Dla gałęzi swierka droga do wlasnego pnia wiedzie wzdluz gałęzi -
        kilka metrow. Droga do pnia brzozy wiedzie w dol przez PUSTE POWIETRZE,
        a tam nie ma po czym isc. Wiec gałąź zostanie przy swierku.

    JAK TO POLICZYC:
        1. Zmniejsz chmure do voxeli (szescianikow), zeby bylo szybciej.
        2. Zbuduj GRAF: kazdy voxel to wierzcholek; polacz voxele blizsze niz
           GRAF_MAX_DLUGOSC_KRAWEDZI. Dlugosc krawedzi = odleglosc w metrach.
           Przez powietrze nie ma krawedzi, bo nie ma tam voxeli.
        3. Oznacz voxele pni jako PUNKTY STARTOWE (po jednym zbiorze na drzewo).
        4. Odpal algorytm Dijkstry ze WSZYSTKICH startow jednoczesnie. Dla
           kazdego voxela dostajesz: do ktorego startu jest najblizej IDAC PO
           GRAFIE. To jest wlasnie przypisanie do drzewa.
        5. Przenies wynik z voxeli na wszystkie punkty.

    Dijkstra to klasyczny algorytm najkrotszej sciezki - ten sam, ktory
    liczy trase w nawigacji samochodowej. scipy ma go gotowego.
    """
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import dijkstra

    print(f"\n[KROK 6b] Segmentacja grafowa "
          f"(voxel {P.GRAF_ROZMIAR_VOXELA} m, "
          f"krawedz max {P.GRAF_MAX_DLUGOSC_KRAWEDZI} m)")

    if len(pnie_df) == 0:
        return np.zeros(len(punkty), dtype=np.int32)

    # --- 1. VOXELIZACJA --------------------------------------------------
    v = P.GRAF_ROZMIAR_VOXELA
    klucze = np.floor(punkty / v).astype(np.int64)
    # unikalne voxele; `odwrotnosc` mowi, do ktorego voxela trafil kazdy punkt
    _, pierwszy_idx, odwrotnosc = np.unique(
        klucze, axis=0, return_index=True, return_inverse=True)
    odwrotnosc = odwrotnosc.ravel()
    n_voxeli = len(pierwszy_idx)

    # srodek kazdego voxela = srednia polozen punktow w nim
    srodki = np.zeros((n_voxeli, 3))
    licznik = np.bincount(odwrotnosc, minlength=n_voxeli).astype(float)
    for os in range(3):
        srodki[:, os] = np.bincount(odwrotnosc, weights=punkty[:, os],
                                    minlength=n_voxeli) / licznik
    # wysokosc nad gruntem dla voxela = srednia z jego punktow
    wys_voxela = (np.bincount(odwrotnosc, weights=wysokosc_ng,
                              minlength=n_voxeli) / licznik)

    print(f"         voxeli: {n_voxeli:,} "
          f"(z {len(punkty):,} punktow, redukcja {len(punkty)/n_voxeli:.0f}x)")

    # --- 2. BUDOWA GRAFU ------------------------------------------------
    kd = cKDTree(srodki)
    k = min(P.GRAF_SASIEDZI + 1, n_voxeli)
    odl, sas = kd.query(srodki, k=k, workers=-1)

    # odrzucamy kolumne 0 (voxel sam ze soba) i krawedzie za dlugie
    odl, sas = odl[:, 1:], sas[:, 1:]
    zrodlo = np.repeat(np.arange(n_voxeli), odl.shape[1])
    cel = sas.ravel()
    odleglosc_rzeczywista = odl.ravel()

    # Czy krawedz istnieje - decyduje PRAWDZIWA odleglosc w metrach.
    ok = odleglosc_rzeczywista <= P.GRAF_MAX_DLUGOSC_KRAWEDZI
    zrodlo, cel = zrodlo[ok], cel[ok]

    # Ile ta krawedz KOSZTUJE - tu wchodzi kara za ruch w poziomie.
    # Uwaga na roznice: "czy mozna przejsc" to geometria, "ile to kosztuje"
    # to nasza decyzja. Dlatego liczone osobno.
    roznica = srodki[cel] - srodki[zrodlo]
    waga = np.sqrt(P.GRAF_KARA_POZIOMA * (roznica[:, 0] ** 2 + roznica[:, 1] ** 2)
                   + roznica[:, 2] ** 2)
    # Dijkstra nie przyjmuje wag zerowych jako krawedzi, wiec minimum 1 mm
    waga = np.maximum(waga, 0.001)

    graf = coo_matrix((waga, (zrodlo, cel)),
                      shape=(n_voxeli, n_voxeli)).tocsr()
    print(f"         krawedzi w grafie: {len(waga):,}")

    # --- 3. PUNKTY STARTOWE (voxele pni) --------------------------------
    # Voxel jest startem dla drzewa, jesli lezy w plastrze pni i jest blisko
    # (w poziomie) wykrytej pozycji tego pnia.
    pozycje_pni = pnie_df[["x", "y"]].to_numpy()
    kd_pnie = cKDTree(pozycje_pni)
    odl_do_pnia, nr_pnia = kd_pnie.query(srodki[:, :2], workers=-1)

    w_plastrze = ((wys_voxela >= P.WARSTWA_PNI_DOL) &
                  (wys_voxela <= P.WARSTWA_PNI_GORA))
    # promien 0.8 m: z zapasem obejmuje nawet grube pnie
    jest_startem = w_plastrze & (odl_do_pnia < 0.8)

    starty = np.nonzero(jest_startem)[0]
    drzewo_startu = nr_pnia[starty] + 1          # numerujemy drzewa od 1

    print(f"         voxeli startowych (pnie): {len(starty)} "
          f"dla {len(pnie_df)} drzew")

    if len(starty) == 0:
        print("         UWAGA: brak startow, wracam do metody prostej")
        return krok6_przypisz_punkty(punkty, pnie_df)

    # --- 4. DIJKSTRA Z WIELU ZRODEL -------------------------------------
    # min_only=True: nie licz osobnej macierzy dla kazdego startu (byloby
    # ogromne), tylko dla kazdego voxela zapamietaj NAJBLIZSZY start.
    # `zrodla` zwraca, ktory to byl start.
    _, _, zrodla = dijkstra(graf, directed=False, indices=starty,
                            return_predecessors=True, min_only=True)

    # mapowanie: indeks voxela-startu -> numer drzewa
    start_na_drzewo = np.zeros(n_voxeli, dtype=np.int32)
    start_na_drzewo[starty] = drzewo_startu

    id_voxela = np.zeros(n_voxeli, dtype=np.int32)
    osiagniete = zrodla >= 0                      # -9999 gdy nieosiagalny
    id_voxela[osiagniete] = start_na_drzewo[zrodla[osiagniete]]

    print(f"         voxeli osiagnietych przez sciezke: "
          f"{int(osiagniete.sum()):,} / {n_voxeli:,} "
          f"({osiagniete.mean()*100:.1f}%)")

    # --- 4b. ZABEZPIECZENIE: voxele nieosiagalne -------------------------
    # Czesc chmury bywa ODCIETA od wszystkich pni - sciezka do nich nie
    # istnieje. Powody sa calkiem prozaiczne i wystepuja w kazdym realnym
    # skanie TLS:
    #   - zaslonieta czesc pnia: skaner nie widzial 2 m pnia, wiec w chmurze
    #     jest dziura i cala korona nad nia "wisi" bez polaczenia z dolem
    #   - cienki czubek drzewa, ktory ledwo zostal zeskanowany
    #   - fragmenty koron sasiadow wchodzace w kadr z boku
    #
    # GDYBYSMY JE PO CICHU WYRZUCILI, stalaby sie rzecz najgorsza z mozliwych:
    # drzewo straciloby wlasny czubek, jego wysokosc byla by za mala - a NIC
    # w wynikach by na to nie wskazywalo. (Dokladnie to sie stalo przy
    # budowaniu tego skryptu: trzy najwyzsze drzewa mialy wysokosc zanizona
    # o 3-8 m, a wszystkie inne liczby wygladaly bez zarzutu.)
    #
    # Dlatego przypisujemy je do drzewa NAJBLIZSZEGO PRZYPISANEGO VOXELA W 3D
    # i RAPORTUJEMY, ile ich bylo.
    # Dlaczego tak, a nie po prostu "najblizszy pien"? Bo odcieta czesc
    # korony lezy zwykle bezposrednio nad resztą tej samej korony - a nie
    # koniecznie nad wlasnym pniem (galezie sie przewieszaja). Patrzenie
    # na najblizszego PRZYPISANEGO sasiada w 3D trafia wtedy lepiej.
    nieosiagalne = ~osiagniete
    if nieosiagalne.any() and osiagniete.any():
        kd_ok = cKDTree(srodki[osiagniete])
        idx_ok = np.nonzero(osiagniete)[0]
        odl_sas, i_sas = kd_ok.query(srodki[nieosiagalne], workers=-1)
        id_voxela[nieosiagalne] = id_voxela[idx_ok[i_sas]]

        # Jesli najblizszy przypisany sasiad jest bardzo daleko, to ten
        # fragment chmury nie nalezy do niczego sensownego - zostawiamy 0.
        bardzo_daleko = np.nonzero(nieosiagalne)[0][odl_sas > 3.0]
        id_voxela[bardzo_daleko] = 0

        print(f"         voxeli nieosiagalnych -> wg sasiada 3D: "
              f"{int(nieosiagalne.sum() - len(bardzo_daleko)):,} "
              f"(porzucone: {len(bardzo_daleko):,})")

    # --- 5. Z VOXELI NA PUNKTY ------------------------------------------
    id_drzewa = id_voxela[odwrotnosc]

    # Grunt nie nalezy do zadnego drzewa - odcinam go, zeby nie zaburzal
    # dalszych obliczen (zwlaszcza objetosci i liczby punktow drzewa).
    id_drzewa[wysokosc_ng < 0.3] = 0

    print(f"         przypisano: {int((id_drzewa > 0).sum()):,} punktow")
    print(f"         nieprzypisane: {int((id_drzewa == 0).sum()):,}")

    return id_drzewa.astype(np.int32)


# ======================================================================
# KROK 7: POMIAR PIERSNICY (DBH)
# ======================================================================
def dopasuj_okrag(x, y):
    """
    Dopasowuje okrag do zbioru punktow 2D. Zwraca (srodek_x, srodek_y, promien).

    MATEMATYKA (metoda algebraiczna Kasy):
        Rownanie okregu:  (x-a)^2 + (y-b)^2 = r^2
        Rozwijamy:        x^2 + y^2 = 2a*x + 2b*y + (r^2 - a^2 - b^2)
                          [ znane ]   [ liniowe wzgledem a, b, c    ]

        Podstawiajac c = r^2 - a^2 - b^2 dostajemy UKLAD ROWNAN LINIOWYCH:
            2a*x + 2b*y + c = x^2 + y^2
        a to juz zwykla regresja liniowa - numpy rozwiaze ja jedna komenda
        metoda najmniejszych kwadratow. Na koncu wracamy do promienia:
            r = sqrt(c + a^2 + b^2)

        Dzieki temu nie trzeba zadnej iteracji ani optymalizacji - wynik
        wychodzi od razu, w mikrosekundach.
    """
    A = np.column_stack([2 * x, 2 * y, np.ones(len(x))])
    b = x ** 2 + y ** 2
    (a, b_sr, c), *_ = np.linalg.lstsq(A, b, rcond=None)
    pod_pierwiastkiem = c + a ** 2 + b_sr ** 2
    if pod_pierwiastkiem <= 0:
        return None
    return a, b_sr, np.sqrt(pod_pierwiastkiem)


def dopasuj_okrag_odpornie(x, y, iteracje=3, prog_sigma=2.0):
    """
    Dopasowanie okregu odporne na punkty odstajace.

    PO CO:
        W plastrze na 1.3 m obok pnia prawie zawsze trafia sie cos jeszcze:
        kawalek galezi, lisc, pnacze, mech. Zwykle dopasowanie potraktuje je
        powaznie i rozciagnie okrag - piersnica wyjdzie za duza.

    JAK:
        1. Dopasuj okrag do wszystkich punktow.
        2. Sprawdz, jak daleko kazdy punkt lezy od obwodu tego okregu.
        3. Wyrzuc te, ktore odstaja o wiecej niz 2 sigma.
        4. Dopasuj ponownie do tego, co zostalo. Powtorz kilka razy.

        To uproszczona wersja tego, co robi RANSAC - i w praktyce wystarcza.
    """
    maska = np.ones(len(x), dtype=bool)

    for _ in range(iteracje):
        wynik = dopasuj_okrag(x[maska], y[maska])
        if wynik is None:
            return None
        a, b, r = wynik

        odchylki = np.abs(np.sqrt((x - a) ** 2 + (y - b) ** 2) - r)
        prog = odchylki[maska].mean() + prog_sigma * odchylki[maska].std()
        nowa_maska = odchylki < max(prog, 0.005)   # min. 5 mm tolerancji

        if nowa_maska.sum() < max(P.DBH_MIN_PUNKTOW, 6):
            break
        if (nowa_maska == maska).all():
            break
        maska = nowa_maska

    wynik = dopasuj_okrag(x[maska], y[maska])
    if wynik is None:
        return None
    a, b, r = wynik

    # --- MIARY JAKOSCI --------------------------------------------------
    # UWAGA NA ISTOTNY SZCZEGOL: blad liczymy na punktach ZACHOWANYCH
    # (bo to one tworza okrag), ale POKRYCIE i PUSTOSC na WSZYSTKICH.
    # Gdyby liczyc je tez tylko na zachowanych, miary bylyby bezuzyteczne:
    # dopasowanie odporne wyrzuca punkty tak dlugo, az reszta lezy na okregu,
    # wiec "na zachowanych" kazdy klaks lisci wyglada jak idealny pien.

    # 1. Sredni blad: jak dobrze punkty leza na okregu (w metrach).
    #    Dla dobrego pomiaru na TLS: 0.003-0.015 m.
    reszty = np.abs(np.sqrt((x[maska] - a) ** 2 + (y[maska] - b) ** 2) - r)
    sredni_blad = float(reszty.mean())

    # 3. PUSTOSC SRODKA - najskuteczniejszy test "pien czy krzak".
    #
    #    Przekroj pnia to PIERSCIEN: punkty sa na obwodzie, a w srodku nie ma
    #    nic, bo skaner nie widzi przez drewno. Kepa galezi albo krzak jest
    #    WYPELNIONA punktami na wylot.
    #
    #    Liczymy wiec, jaka czesc punktow NIE lezy w srodkowych 70% promienia:
    #       pustosc = 1  -> idealny pierscien, pusty w srodku (pien)
    #       pustosc = 0.7 i mniej -> bryla wypelniona punktami (krzak, galezie)
    #
    #    Na danych testowych uzytkownika: prawdziwe pnie mialy 0.99-1.00,
    #    a pozostale skupiska mediane 0.73. Rozdzial jest bardzo czysty.
    odl_od_srodka = np.sqrt((x - a) ** 2 + (y - b) ** 2)
    pustosc = float(1.0 - (odl_od_srodka < 0.7 * r).mean())

    # 2. Pokrycie katowe: na jakim kacie punkty NAPRAWDE otaczaja srodek.
    #
    #    Dziele okrag na 36 sektorow po 10 stopni i licze, ile z nich zawiera
    #    chociaz jeden punkt. Pokrycie = (zajete sektory / 36) * 360 stopni.
    #
    #    PIERWSZA WERSJA TEGO KODU LICZYLA TO INACZEJ - jako 360 stopni minus
    #    najwieksza przerwa miedzy sasiednimi punktami - i BYLA ZEPSUTA.
    #    Przy dwoch skupiskach punktow po przeciwnych stronach (co sie zdarza,
    #    gdy dwa osobne pnie zostana zlane w jeden klaster) najwieksza przerwa
    #    wynosi tylko ~90 stopni, wiec wychodzilo "pokrycie 270 stopni" -
    #    wynik znakomity, a pomiar byl kompletna bzdura. Jeden zabladzony
    #    punkt w srodku przerwy robil to samo.
    #    Zliczanie sektorow nie da sie tak oszukac: dwa skupiska zajmuja dwa
    #    kawalki okregu i pokrycie uczciwie wychodzi male.
    katy = np.arctan2(y - b, x - a)
    sektory = ((katy + np.pi) / (2 * np.pi) * 36).astype(int) % 36
    pokrycie = float(len(np.unique(sektory)) / 36 * 360)

    return a, b, r, sredni_blad, pokrycie, pustosc, int(maska.sum())


def krok7_zmierz_dbh(punkty, wysokosc_ng, id_drzewa, pnie_df):
    """
    Mierzy piersnice kazdego drzewa.

    PIERSNICA (DBH, Diameter at Breast Height) to srednica pnia zmierzona
    na wysokosci 1.3 m nad gruntem. Dlaczego 1.3 m a nie u podstawy? Bo przy
    ziemi pien ma nabiegi korzeniowe i pomiar bylby nieporownywalny miedzy
    drzewami. 1.3 m to umowa, ktorej trzyma sie cala lesnictwo w Europie.

    JAK LICZYMY:
        1. Wez punkty tego drzewa z przedzialu 1.3 +/- 0.05 m nad gruntem.
        2. Spojrz na nie z gory (odrzuc Z) - zobaczysz pierscien punktow.
        3. Dopasuj do tego pierscienia okrag.
        4. DBH = 2 * promien.
    """
    print(f"\n[KROK 7] Mierze piersnice na {P.DBH_WYSOKOSC} m "
          f"(plaster +/-{P.DBH_GRUBOSC_PLASTRA/2*100:.0f} cm)")

    dol = P.DBH_WYSOKOSC - P.DBH_GRUBOSC_PLASTRA / 2
    gora = P.DBH_WYSOKOSC + P.DBH_GRUBOSC_PLASTRA / 2
    w_plastrze = (wysokosc_ng >= dol) & (wysokosc_ng <= gora)

    wyniki = []
    powody = {"za_malo_punktow": 0, "zly_okrag": 0, "za_duzy_blad": 0,
              "poza_zakresem": 0, "maly_kat": 0, "wypelniony_srodek": 0}

    def pusty(nr, n, powod):
        powody[powod] += 1
        return {"id_drzewa": nr, "dbh_m": np.nan,
                "dbh_srodek_x": np.nan, "dbh_srodek_y": np.nan,
                "dbh_blad_dopasowania_m": np.nan,
                "dbh_pokrycie_katowe_deg": np.nan,
                "dbh_liczba_punktow": n,
                "dbh_uwagi": powod}

    # Pozycje pni - wokol nich bedziemy szukac okregu.
    pozycje = pnie_df[["x", "y"]].to_numpy()

    for nr in range(1, len(pnie_df) + 1):
        maska = w_plastrze & (id_drzewa == nr)
        n = int(maska.sum())

        if n < P.DBH_MIN_PUNKTOW:
            wyniki.append(pusty(nr, n, "za_malo_punktow"))
            continue

        xs, ys = punkty[maska, 0], punkty[maska, 1]

        # --- OGRANICZENIE DO OKOLIC PNIA ---------------------------------
        # Do drzewa naleza tez galezie - i w gestym lesie w plastrze 1.3 m
        # jest ich mnostwo, czasem kilka metrow od pnia. Gdyby dopasowywac
        # okrag do wszystkiego, wyszedlby okrag o srednicy 3 m zamiast 30 cm.
        # (Tak wlasnie bylo: 30 z 64 drzew odpadalo jako "poza_zakresem".)
        #
        # Robimy to w dwoch podejsciach:
        #   1. Bierzemy punkty blisko WYKRYTEJ POZYCJI pnia i dopasowujemy
        #      wstepny okrag - to daje zgrubny srodek i promien.
        #   2. Bierzemy punkty blisko TEGO okregu i dopasowujemy jeszcze raz,
        #      juz precyzyjnie.
        # Drugie podejscie jest wazne, bo pozycja z DBSCAN to srodek skupiska
        # punktow pnia, ktore przy jednostronnym oswietleniu skanera bywa
        # przesuniete wzgledem prawdziwej osi pnia.
        px, py = pozycje[nr - 1]
        promien_szukania = P.MAX_SREDNICA_PNIA / 2 + 0.10

        blisko = np.hypot(xs - px, ys - py) < promien_szukania
        if blisko.sum() < P.DBH_MIN_PUNKTOW:
            wyniki.append(pusty(nr, int(blisko.sum()), "za_malo_punktow"))
            continue

        wstepny = dopasuj_okrag_odpornie(xs[blisko], ys[blisko])
        if wstepny is None:
            wyniki.append(pusty(nr, n, "zly_okrag"))
            continue

        a0, b0, r0 = wstepny[0], wstepny[1], wstepny[2]
        # pierscien wokol wstepnego okregu: +/- 40% promienia, min. 5 cm
        margines = max(0.4 * r0, 0.05)
        odl_od_okregu = np.abs(np.hypot(xs - a0, ys - b0) - r0)
        pierscien = odl_od_okregu < margines

        if pierscien.sum() < P.DBH_MIN_PUNKTOW:
            pierscien = blisko          # awaryjnie wracamy do podejscia 1

        wynik = dopasuj_okrag_odpornie(xs[pierscien], ys[pierscien])
        if wynik is None:
            wyniki.append(pusty(nr, n, "zly_okrag"))
            continue

        a, b, r, blad, pokrycie, pustosc, n_uzytych = wynik
        srednica = 2 * r

        # --- KONTROLA JAKOSCI -------------------------------------------
        # Lepiej zwrocic "nie wiem" niz liczbe, ktorej nie da sie obronic.
        # Kazde odrzucenie jest zapisane w kolumnie dbh_uwagi, zebys wiedzial,
        # ktore drzewa obejrzec recznie w CloudCompare.
        if not (P.MIN_SREDNICA_PNIA <= srednica <= P.MAX_SREDNICA_PNIA):
            wyniki.append(pusty(nr, n, "poza_zakresem"))
            continue
        if blad > P.DBH_MAX_BLAD_DOPASOWANIA:
            wyniki.append(pusty(nr, n, "za_duzy_blad"))
            continue

        # Male pokrycie katowe ODRZUCAMY, a nie tylko oznaczamy. Na prawdziwym
        # skanie to najskuteczniejszy filtr falszywych pni: skupisko galezi
        # nigdy nie otacza srodka dookola, a pien prawie zawsze tak.
        if pokrycie < P.DBH_MIN_POKRYCIE_KATOWE:
            wyniki.append(pusty(nr, n, "maly_kat"))
            continue
        if pustosc < P.DBH_MIN_PUSTOSC:
            wyniki.append(pusty(nr, n, "wypelniony_srodek"))
            continue
        uwagi = "ok" if pokrycie >= 270 else "niepewny_czesciowy_luk"

        wyniki.append({
            "id_drzewa": nr,
            "dbh_m": round(srednica, 4),
            "dbh_srodek_x": round(a, 3),
            "dbh_srodek_y": round(b, 3),
            "dbh_blad_dopasowania_m": round(blad, 4),
            "dbh_pokrycie_katowe_deg": round(pokrycie, 1),
            "dbh_liczba_punktow": n_uzytych,
            "dbh_uwagi": uwagi,
        })

    df = pd.DataFrame(wyniki)
    udane = int(df.dbh_m.notna().sum())
    print(f"         zmierzono: {udane}/{len(pnie_df)} drzew")

    for powod, ile in powody.items():
        if ile:
            print(f"           - {powod}: {ile}")

    if udane:
        print(f"         DBH: {df.dbh_m.min():.3f} - {df.dbh_m.max():.3f} m "
              f"(srednio {df.dbh_m.mean():.3f} m)")
        print(f"         sredni blad dopasowania okregu: "
              f"{df.dbh_blad_dopasowania_m.mean()*1000:.1f} mm")
        print(f"         srednie pokrycie katowe pnia: "
              f"{df.dbh_pokrycie_katowe_deg.mean():.0f} stopni")

    return df


# ======================================================================
# KROK 8: WYSOKOSC DRZEW
# ======================================================================
def oznacz_posusz_i_rozwidlenia(tabela, punkty, wysokosc_ng, id_drzewa):
    """
    Dokleja do tabeli dwie grupy kolumn z podpowiedziami o drzewach
    problematycznych. NIE usuwa niczego i nie zmienia pomiarow - tylko
    oznacza, zebys mogl sam zdecydowac, co odfiltrowac.

    A) POSUSZ STOJACY (drzewo martwe)
       Zywe drzewo ma nad soba korone. Martwy, zlamany pien to sam slup.
       Liczymy w gornych 40% wysokosci drzewa:
         udzial_punktow_gory  - jaka czesc punktow drzewa tam jest
         promien_korony_m     - jak szeroko sa rozrzucone wokol osi
       Obie male -> prawdopodobnie posusz.

    B) ROZWIDLENIA (pnie dwuodnogowe)
       Dwie odnogi jednego drzewa maja osie, ktore schodza sie ku dolowi.
       Przedluzamy osie obu pni w dol i sprawdzamy, czy sie spotykaja.
       Pary dostaja wspolny numer w kolumnie grupa_rozwidlenia.
    """
    print("\n[KROK 8b] Szukam posuszu i rozwidlen")

    # ---------- A) POSUSZ ----------
    udzialy, promienie = [], []
    for _, w in tabela.iterrows():
        nr = int(w.id_drzewa)
        maska = id_drzewa == nr
        n_all = int(maska.sum())
        if n_all < 50 or not np.isfinite(w.get("wysokosc_m", np.nan)):
            udzialy.append(np.nan); promienie.append(np.nan)
            continue

        h_drzewa = wysokosc_ng[maska]
        gora = h_drzewa > 0.6 * w["wysokosc_m"]
        udzial = float(gora.mean())

        if gora.sum() >= 10:
            px, py = w["pozycja_x"], w["pozycja_y"]
            odl = np.hypot(punkty[maska][gora, 0] - px,
                           punkty[maska][gora, 1] - py)
            promien = float(np.percentile(odl, 90))
        else:
            promien = 0.0

        udzialy.append(round(udzial, 4))
        promienie.append(round(promien, 2))

    tabela["udzial_punktow_gory"] = udzialy
    tabela["promien_korony_m"] = promienie
    tabela["prawdopodobnie_martwe"] = (
        (tabela.udzial_punktow_gory < P.MARTWE_PROG_UDZIALU_GORY) &
        (tabela.promien_korony_m < P.MARTWE_PROG_PROMIENIA_M))

    ile_martwych = int(tabela.prawdopodobnie_martwe.sum())
    print(f"          oznaczono jako prawdopodobny posusz: {ile_martwych} "
          f"z {len(tabela)}")

    # ---------- B) ROZWIDLENIA ----------
    tabela["grupa_rozwidlenia"] = 0
    if {"os_spadek_x", "os_spadek_y"}.issubset(tabela.columns):
        hs = P.ROZWIDLENIE_WYSOKOSC_SPRAWDZENIA_M
        # polozenie osi kazdego pnia przedluzone w dol do wysokosci hs
        px = tabela.pozycja_x.to_numpy() + tabela.os_spadek_x.to_numpy() * (hs - 1.3)
        py = tabela.pozycja_y.to_numpy() + tabela.os_spadek_y.to_numpy() * (hs - 1.3)

        grupa = 0
        przypisane = np.zeros(len(tabela), dtype=int)
        for i in range(len(tabela)):
            for j in range(i + 1, len(tabela)):
                if np.hypot(px[i] - px[j], py[i] - py[j]) \
                        < P.ROZWIDLENIE_MAX_ODLEGLOSC_M:
                    if przypisane[i] == 0 and przypisane[j] == 0:
                        grupa += 1
                        przypisane[i] = przypisane[j] = grupa
                    elif przypisane[i] == 0:
                        przypisane[i] = przypisane[j]
                    elif przypisane[j] == 0:
                        przypisane[j] = przypisane[i]
        tabela["grupa_rozwidlenia"] = przypisane
        ile_par = int(grupa)
        print(f"          wykryto grup rozwidlen: {ile_par} "
              f"(obejmuja {int((przypisane > 0).sum())} pni)")
        if ile_par:
            print(f"          UWAGA: pnie z tym samym numerem w kolumnie "
                  f"grupa_rozwidlenia to\n          prawdopodobnie odnogi "
                  f"JEDNEGO drzewa - nie licz ich podwojnie.")

    return tabela


def krok8_zmierz_wysokosci(wysokosc_ng, id_drzewa, liczba_drzew):
    """
    Wysokosc drzewa = najwyzszy punkt nalezacy do tego drzewa,
                      mierzony nad gruntem.

    Brzmi banalnie i jest banalne - CALA trudnosc tego pomiaru siedzi
    w krokach 2, 3 i 6, nie tutaj:

      - gdyby szum nie byl usuniety (KROK 2), jakis punkt wiszacy 5 m nad
        korona zawyzylby wysokosc;
      - gdyby grunt byl zly (KROK 3), wszystkie wysokosci bylyby przesuniete;
      - gdyby segmentacja byla zla (KROK 6), czubek sasiada trafilby do
        naszego drzewa.

    Dlatego: jesli wysokosci wychodza dziwne, NIE szukaj bledu tutaj.
    """
    print(f"\n[KROK 8] Mierze wysokosci drzew")

    wyniki = []
    for nr in range(1, liczba_drzew + 1):
        maska = id_drzewa == nr
        if not maska.any():
            wyniki.append({"id_drzewa": nr, "wysokosc_m": np.nan,
                           "liczba_punktow_drzewa": 0})
            continue
        wyniki.append({
            "id_drzewa": nr,
            "wysokosc_m": round(float(wysokosc_ng[maska].max()), 3),
            "liczba_punktow_drzewa": int(maska.sum()),
        })

    df = pd.DataFrame(wyniki)
    ok = df.wysokosc_m.notna()
    if ok.any():
        print(f"         wysokosci: {df.loc[ok,'wysokosc_m'].min():.2f} - "
              f"{df.loc[ok,'wysokosc_m'].max():.2f} m "
              f"(srednio {df.loc[ok,'wysokosc_m'].mean():.2f} m)")
    return df


# ======================================================================
# KROK 9: ZAPIS WYNIKOW
# ======================================================================
def krok9_zapisz(tabela, punkty, id_drzewa, wysokosc_ng, las_oryginalny,
                 katalog, nazwa_bazowa):
    """
    Zapisuje dwa pliki:

      <nazwa>_drzewa.csv   tabela: jedno drzewo = jeden wiersz
      <nazwa>_segmenty.laz chmura z dodatkowymi polami, do podgladu
                           w CloudCompare

    W pliku .laz dopisuje dwa wlasne pola ("extra dimensions"):
      treeID_pred   - numer drzewa, do ktorego punkt zostal przypisany
      wys_nad_grunt - wysokosc punktu nad gruntem

    Dzieki temu w CloudCompare mozesz pokolorowac chmure po treeID_pred
    i NA WLASNE OCZY sprawdzic, czy segmentacja ma sens. Rob to zawsze -
    liczby w CSV moga wygladac rozsadnie, a segmentacja byc rozwalona.
    """
    print(f"\n[KROK 9] Zapisuje wyniki")
    katalog.mkdir(parents=True, exist_ok=True)

    sciezka_csv = katalog / f"{nazwa_bazowa}_drzewa.csv"
    tabela.to_csv(sciezka_csv, index=False)
    print(f"         {sciezka_csv}")

    naglowek = laspy.LasHeader(point_format=6, version="1.4")
    naglowek.scales = np.array([0.001, 0.001, 0.001])
    naglowek.offsets = np.floor(punkty.min(axis=0))
    naglowek.add_extra_dim(laspy.ExtraBytesParams(name="treeID_pred", type=np.int32))
    naglowek.add_extra_dim(laspy.ExtraBytesParams(name="wys_nad_grunt", type=np.float32))

    out = laspy.LasData(naglowek)
    out.x, out.y, out.z = punkty[:, 0], punkty[:, 1], punkty[:, 2]
    out.treeID_pred = id_drzewa
    out.wys_nad_grunt = wysokosc_ng.astype(np.float32)

    sciezka_laz = katalog / f"{nazwa_bazowa}_segmenty.laz"
    out.write(sciezka_laz)
    print(f"         {sciezka_laz}")

    return sciezka_csv, sciezka_laz


# ======================================================================
# GLOWNY PRZEBIEG
# ======================================================================
def main():
    ap = argparse.ArgumentParser(
        description="Inwentaryzacja lasu z chmury punktow TLS (.las/.laz)")
    ap.add_argument("plik", type=Path, help="plik wejsciowy .las lub .laz")
    ap.add_argument("--wyniki", type=Path, default=Path("results"),
                    help="katalog na wyniki (domyslnie: wyniki/)")
    ap.add_argument("--metoda", choices=["prosta", "graf"], default="graf",
                    help="segmentacja: 'prosta' = najblizszy pien (szybka, "
                         "myli sie przy przewieszonych galeziach), "
                         "'graf' = najkrotsza sciezka przez chmure "
                         "(wolniejsza, dokladniejsze wysokosci). Domyslnie: graf")
    ap.add_argument("--detekcja", choices=["sledzenie", "plaster"],
                    default="sledzenie",
                    help="wykrywanie pni: 'sledzenie' = lancuchy okregow przez "
                         "wiele plastrow (odporne na krzaki, zalecane), "
                         "'plaster' = jeden plaster na 1-4 m (szybsze, "
                         "myli krzaki z drzewami). Domyslnie: sledzenie")
    ap.add_argument("--srodek", type=float, nargs=2, metavar=("X","Y"),
                    default=None,
                    help="wspolrzedne stanowiska skanera, np. --srodek 0 0. "
                         "Podaj je, jesli znasz - oszacowanie automatyczne "
                         "potrafi sie mylic o kilka metrow, a na WYCINKU skanu "
                         "jest bezwartosciowe.")
    ap.add_argument("--promien", type=float, default=None,
                    help="ogranicz analize do kola o tym promieniu wokol "
                         "srodka skanu, w metrach (np. 20)")
    ap.add_argument("--przyrostek", default="",
                    help="dopisek do nazw plikow wyjsciowych, np. _prosta")
    ap.add_argument("--pokrycie", type=float, default=None, metavar="ST",
                    help="minimalne pokrycie katowe pnia w stopniach "
                         "(domyslnie 180; skan ze statywu: 90; "
                         "porzadnie obchodzona powierzchnia: 250)")
    ap.add_argument("--sciana", type=float, default=None, metavar="X",
                    help="minimalna 'sciana pnia' 0-1 (domyslnie 0.6); "
                         "podaj 0, zeby wylaczyc")
    ap.add_argument("--smuklosc", type=float, nargs=2, default=None,
                    metavar=("MIN", "MAX"),
                    help="dopuszczalna smuklosc h/d (domyslnie 25 150); "
                         "podaj 0 0, zeby wylaczyc filtr")
    ap.add_argument("--sledzenie-gora", type=float, default=None, metavar="M",
                    help="dokad w gore sledzic pien okregami [m] "
                         "(domyslnie 6.0)")
    ap.add_argument("--min-plastrow", type=int, default=None, metavar="N",
                    help="ile plastrow musi miec lancuch, by byl drzewem "
                         "(domyslnie 6)")
    ap.add_argument("--min-dbh", type=float, default=None, metavar="M",
                    help="najcienszsze drzewo, jakie ma wejsc do tabeli, "
                         "w METRACH (domyslnie 0.07 = 7 cm; "
                         "podaj 0, zeby nie odrzucac nic)")
    args = ap.parse_args()

    if args.promien is not None:
        P.MAX_PROMIEN_ANALIZY = args.promien

    if args.pokrycie is not None:
        P.DBH_MIN_POKRYCIE_KATOWE = args.pokrycie
        print(f"[USTAWIENIE] min. pokrycie katowe: "
              f"{P.DBH_MIN_POKRYCIE_KATOWE:g} stopni")

    if args.sciana is not None:
        P.SCIANA_MIN = args.sciana
        print(f"[USTAWIENIE] filtr sciany pnia: >= {P.SCIANA_MIN:g}")

    if args.smuklosc is not None:
        P.SMUKLOSC_MIN, P.SMUKLOSC_MAX = args.smuklosc
        print(f"[USTAWIENIE] filtr smuklosci: "
              f"{P.SMUKLOSC_MIN:g} - {P.SMUKLOSC_MAX:g}"
              + ("  (WYLACZONY)" if not (P.SMUKLOSC_MIN or P.SMUKLOSC_MAX)
                 else ""))

    if args.sledzenie_gora is not None:
        P.SLEDZENIE_GORA = args.sledzenie_gora
    if args.min_plastrow is not None:
        P.SLEDZENIE_MIN_PLASTROW = args.min_plastrow

    if args.min_dbh is not None:
        P.MIN_DBH_RAPORTOWANIA = args.min_dbh
        # Szukamy z zapasem 1.5 cm PONIZEJ progu raportowania, zeby drzewo
        # dokladnie na granicy nie wypadalo z powodu bledu pomiaru.
        P.MIN_SREDNICA_PNIA = max(0.03, args.min_dbh - 0.015)
        print(f"[USTAWIENIE] raportuje drzewa od "
              f"{P.MIN_DBH_RAPORTOWANIA*100:.1f} cm piersnicy "
              f"(szukam od {P.MIN_SREDNICA_PNIA*100:.1f} cm)")

    if not args.plik.exists():
        sys.exit(f"BLAD: nie ma pliku {args.plik}")

    # KAZDY SKAN DOSTAJE WLASNY PODFOLDER.
    # Zamiast wrzucac wszystko na kupe do wyniki/, robimy
    #     wyniki/_S1j__r20/
    # i tam ladują WSZYSTKIE pliki tego skanu. Dzieki temu wyniki dwoch
    # skanow nigdy sie nie pomieszaja, a caly folder mozna skopiowac,
    # spakowac albo wyrzucic jednym ruchem.
    nazwa_bazowa = args.plik.stem + args.przyrostek
    katalog_skanu = args.wyniki / nazwa_bazowa
    katalog_skanu.mkdir(parents=True, exist_ok=True)

    print("=" * 66)
    print("PIPELINE INWENTARYZACJI LASU")
    print("=" * 66)

    punkty_wszystkie, las = krok1_wczytaj(args.plik)
    punkty, _ = krok2_usun_szum(punkty_wszystkie)
    # Surowa chmura nie jest juz potrzebna - zwalniamy pamiec. Przy 27 mln
    # punktow to 600 MB, a dalej beda potrzebne na drzewo kd i na graf.
    del punkty_wszystkie
    dtm_xy, dtm_z = krok3_model_terenu(punkty)
    wysokosc_ng, _ = krok4_normalizuj_wysokosc(punkty, dtm_xy, dtm_z)
    # --- ograniczenie do strefy dobrych danych ---------------------------
    if P.MAX_PROMIEN_ANALIZY and P.MAX_PROMIEN_ANALIZY > 0:
      if args.srodek is not None:
        srodek = np.array(args.srodek, dtype=float)
        print(f"\n[STREFA] Stanowisko skanera PODANE RECZNIE: "
              f"({srodek[0]:.1f}, {srodek[1]:.1f})")
      else:
        # OSZACOWANIE: skaner stoi tam, gdzie punkty sa najgestsze.
        #
        # UWAGA - to jest SLABA heurystyka i trzeba o tym wiedziec:
        #   - gesta sciana roslinnosci potrafi przebic gestosc przy skanerze
        #   - na WYCINKU skanu (a nie calym skanie) jest zupelnie bez sensu,
        #     bo prawdziwe stanowisko moze lezec poza wycinkiem
        # Na danych testowych mylila sie o ok. 5 m. Jesli znasz polozenie
        # stanowiska - podaj je przez --srodek X Y, zamiast polegac na tym.
        krok = 1.0
        kx = ((punkty[:, 0] - punkty[:, 0].min()) / krok).astype(int)
        ky = ((punkty[:, 1] - punkty[:, 1].min()) / krok).astype(int)
        gest = np.zeros((ky.max() + 1, kx.max() + 1))
        np.add.at(gest, (ky, kx), 1)
        wy, wx = np.unravel_index(np.argmax(gest), gest.shape)
        srodek = np.array([(wx + 0.5) * krok + punkty[:, 0].min(),
                           (wy + 0.5) * krok + punkty[:, 1].min()])
        print(f"\n[STREFA] Stanowisko OSZACOWANE (najgestsze miejsce) na "
              f"({srodek[0]:.1f}, {srodek[1]:.1f})")
        print(f"         to tylko zgadywanie - jesli znasz stanowisko, "
              f"podaj --srodek X Y")
      if True:
        w_zasiegu = np.hypot(punkty[:, 0] - srodek[0],
                             punkty[:, 1] - srodek[1]) <= P.MAX_PROMIEN_ANALIZY
        print(f"         promien analizy {P.MAX_PROMIEN_ANALIZY} m")
        print(f"         zostaje {int(w_zasiegu.sum()):,} z {len(punkty):,} "
              f"punktow ({w_zasiegu.mean()*100:.1f}%)")
        punkty = punkty[w_zasiegu]
        wysokosc_ng = wysokosc_ng[w_zasiegu]

    lancuchy_okregow = None
    if args.detekcja == "sledzenie":
        pnie, lancuchy_okregow = krok5b_sledz_pnie(punkty, wysokosc_ng)
    else:
        pnie = krok5_wykryj_pnie(punkty, wysokosc_ng)

    if len(pnie) == 0:
        sys.exit("\nNie wykryto zadnego drzewa. Sprawdz parametry WARSTWA_PNI_* "
                 "i DBSCAN_* na gorze pliku.")

    if args.metoda == "graf":
        id_drzewa = krok6b_przypisz_punkty_grafowo(punkty, wysokosc_ng, pnie)
    else:
        id_drzewa = krok6_przypisz_punkty(punkty, pnie)

    if args.detekcja == "sledzenie":
        # DBH policzono juz w kroku 5 z calego lancucha okregow - jest
        # dokladniejszy niz pomiar z jednego plastra, wiec go nie przeliczamy.
        dbh = pnie[["dbh_m"]].copy()
        dbh.insert(0, "id_drzewa", np.arange(1, len(pnie) + 1))
        dbh["dbh_blad_dopasowania_m"] = pnie["sredni_blad_okregu_m"].to_numpy()
        dbh["dbh_pokrycie_katowe_deg"] = pnie["srednie_pokrycie_deg"].to_numpy()
        dbh["dbh_liczba_punktow"] = pnie["liczba_plastrow"].to_numpy()
        dbh["dbh_srodek_x"] = pnie["x"].round(3).to_numpy()
        dbh["dbh_srodek_y"] = pnie["y"].round(3).to_numpy()
        pokr = pnie["srednie_pokrycie_deg"].to_numpy()
        ekstr = pnie["dbh_ekstrapolowany"].to_numpy()
        zrodlo = pnie["dbh_zrodlo_wartosci"].to_numpy()
        # UWAGA NA NAZWE: dawniej bylo tu "brak_pnia_na_1.3m", co bylo
        # nieprawda i wprowadzalo w blad. Pien NA OGOL tam jest - widac go
        # golym okiem na podgladzie. Nie udalo sie natomiast dopasowac
        # do niego OKREGU, bo skaner widzial go z jednej strony (na 9F
        # typowo 70-170 stopni luku, 12-45 punktow) albo podszyt stal
        # tak blisko, ze sie z nim zlal. Nazwa mowi teraz, co sie stalo,
        # a srednica zmierzona wyzej jest w osobnej kolumnie.
        dbh["dbh_uwagi"] = np.where(
            zrodlo == "brak", "nie_zmierzono_na_1.3m_patrz_srednica_zmierzona",
            np.where(zrodlo == "oszacowanie_ze_zbieznosci",
                     "oszacowany_ze_zbieznosci_pnia",
                     np.where(pokr >= 270, "ok", "niepewny_czesciowy_luk")))
        ile_ekstr = int((zrodlo == "brak").sum())
        ile_szac = int((zrodlo == "oszacowanie_ze_zbieznosci").sum())
        if ile_szac:
            print(f"\n  {ile_szac} drzew ma piersnice OSZACOWANA ze zbieznosci "
                  f"pnia - podszyt zaslanial\n  1.3 m, wiec wartosc policzono "
                  f"z pomiarow wyzej. Uzywalna, ale oznaczona.")
        if ile_ekstr:
            print(f"\n  UWAGA: dla {ile_ekstr} drzew nie da sie zmierzyc "
                  f"piersnicy na 1.3 m -\n  pien jest tam zasloniety (zwykle "
                  f"przez podszyt). Kolumna dbh_m jest dla nich PUSTA.\n"
                  f"  TO NADAL MOGA BYC PRAWDZIWE DRZEWA. Ich faktycznie "
                  f"zmierzona grubosc\n  jest w kolumnach srednica_zmierzona_m "
                  f"i wysokosc_pomiaru_m.")
        pnie = pnie.drop(columns=["dbh_m"])
    else:
        dbh = krok7_zmierz_dbh(punkty, wysokosc_ng, id_drzewa, pnie)
    wys = krok8_zmierz_wysokosci(wysokosc_ng, id_drzewa, len(pnie))

    # Sklejenie wszystkiego w jedna tabele
    pnie = pnie.reset_index(drop=True)
    pnie.insert(0, "id_drzewa", np.arange(1, len(pnie) + 1))
    pnie = pnie.rename(columns={"x": "pozycja_x", "y": "pozycja_y"})
    if "liczba_punktow_plastra" not in pnie.columns:
        pnie["liczba_punktow_plastra"] = np.nan

    tabela = (pnie
              .merge(dbh, on="id_drzewa")
              .merge(wys, on="id_drzewa"))

    # Pole przekroju - podstawowa wielkosc w dendrometrii, pole kola o
    # srednicy DBH. Suma po drzewach / powierzchnia poletka = zageszczenie
    # drzewostanu (m2/ha), jedna z glownych cech taksacyjnych.
    tabela["pole_przekroju_m2"] = (np.pi * (tabela.dbh_m / 2) ** 2).round(5)

    # --- OZNACZENIE DRZEW BEZ ZAOBSERWOWANEGO GRUNTU ---------------------
    # Dla drzewa stojacego daleko od obszaru, gdzie skaner widzial ziemie,
    # wysokosc gruntu jest zgadywana - a wiec i wysokosc drzewa. Liczymy
    # odleglosc kazdego drzewa od najblizszej komorki z prawdziwym gruntem
    # i oznaczamy te, ktore sa za daleko. NIE usuwamy ich - tylko ostrzegamy.
    kd_grunt = cKDTree(dtm_xy)
    odl_grunt, _ = kd_grunt.query(tabela[["pozycja_x", "pozycja_y"]].to_numpy())
    tabela["odl_od_gruntu_m"] = odl_grunt.round(2)
    tabela["uwagi_grunt"] = np.where(
        odl_grunt <= P.DTM_MAX_ODLEGLOSC_EKSTRAPOLACJI,
        "ok", "wysokosc_niepewna_brak_gruntu")

    niepewne = int((tabela.uwagi_grunt != "ok").sum())
    if niepewne:
        print(f"\n  UWAGA: {niepewne} z {len(tabela)} drzew stoi dalej niz "
              f"{P.DTM_MAX_ODLEGLOSC_EKSTRAPOLACJI} m od obszaru,\n"
              f"  w ktorym skaner widzial grunt. Ich WYSOKOSCI sa niepewne "
              f"(pierśnice pozostaja wiarygodne).\n"
              f"  Patrz kolumna `uwagi_grunt` w tabeli.")

    tabela = oznacz_posusz_i_rozwidlenia(tabela, punkty, wysokosc_ng, id_drzewa)

    kolumny = ["id_drzewa", "pozycja_x", "pozycja_y", "dbh_m", "wysokosc_m",
               "pole_przekroju_m2", "dbh_uwagi", "uwagi_grunt",
               "dbh_blad_dopasowania_m", "dbh_pokrycie_katowe_deg",
               "dbh_liczba_punktow", "odl_od_gruntu_m",
               "liczba_punktow_drzewa",
               # srodek dopasowanego okregu - to DOKLADNIEJSZA pozycja osi pnia
               # niz pozycja_* (ta jest srodkiem skupiska punktow z DBSCAN,
               # a skaner widzi pien tylko z jednej strony, wiec skupisko bywa
               # przesuniete o kilka cm w strone skanera).
               "dbh_srodek_x", "dbh_srodek_y"]
    for extra in ("dbh_do_uzycia_m", "dbh_zrodlo_wartosci",
                  "nachylenie_pnia_deg", "korekta_nachylenia_proc",
                  "dbh_szacowany_m", "srednica_zmierzona_m", "wysokosc_pomiaru_m", "liczba_plastrow", "zakres_pnia_m", "zbieznosc_m_na_m",
                  "srednia_pustosc", "sciana_pnia",
                  "nachylenie_srednicy_cm_na_m",
                  "odleglosc_pomiaru_od_13m",
                  "prawdopodobnie_martwe", "udzial_punktow_gory",
                  "promien_korony_m", "grupa_rozwidlenia"):
        if extra in tabela.columns:
            kolumny.append(extra)
    tabela = tabela[kolumny]

    # --- SMUKLOSC (h/d) + filtr zdrowego rozsadku ------------------------
    # Patrz dlugi komentarz przy SMUKLOSC_MIN w klasie Parametry.
    zrodlo_dbh = (tabela["dbh_do_uzycia_m"] if "dbh_do_uzycia_m" in tabela
                  else tabela["dbh_m"])
    with np.errstate(divide="ignore", invalid="ignore"):
        tabela["smuklosc_h_d"] = (tabela["wysokosc_m"] / zrodlo_dbh).round(1)

    odrzucone = pd.DataFrame()
    if P.SMUKLOSC_MIN or P.SMUKLOSC_MAX or P.SCIANA_MIN:
        sm = tabela["smuklosc_h_d"]
        # Drzewa bez piersnicy albo bez wysokosci maja smuklosc NaN - tych
        # NIE odrzucamy, bo nie wiemy, czy sa niemozliwe. Zostaja w tabeli.
        # UWAGA: wylaczony prog (0) musi dac SERIE samych falszow, a nie
        # liczbe 0 - inaczej dalsze .fillna() wywala sie na float.
        pusta = pd.Series(False, index=tabela.index)
        za_grube = (sm < P.SMUKLOSC_MIN) if P.SMUKLOSC_MIN else pusta.copy()
        za_cienkie = (sm > P.SMUKLOSC_MAX) if P.SMUKLOSC_MAX else pusta.copy()
        # Drugi, niezalezny test: czy pien jest sciana (patrz SCIANA_MIN).
        if P.SCIANA_MIN and "sciana_pnia" in tabela.columns:
            nie_sciana = tabela["sciana_pnia"] < P.SCIANA_MIN
        else:
            nie_sciana = pusta.copy()
        # Trzeci test: czy srednica nie ROSNIE ku gorze (patrz komentarz
        # przy MAX_PRZYROST_SREDNICY_CM_NA_M). Kolumna jest w cm na metr
        # i dla prawdziwego pnia jest UJEMNA.
        if (P.MAX_PRZYROST_SREDNICY_CM_NA_M
                and "nachylenie_srednicy_cm_na_m" in tabela.columns):
            rozszerza = (tabela["nachylenie_srednicy_cm_na_m"]
                         > P.MAX_PRZYROST_SREDNICY_CM_NA_M)
        else:
            rozszerza = pusta.copy()
        zle = (za_grube.fillna(False) | za_cienkie.fillna(False)
               | nie_sciana.fillna(False) | rozszerza.fillna(False))

        if zle.any():
            odrzucone = tabela[zle].copy()
            odrzucone["przyczyna_odrzucenia"] = np.select(
                [za_grube.fillna(False)[zle],
                 za_cienkie.fillna(False)[zle],
                 nie_sciana.fillna(False)[zle],
                 rozszerza.fillna(False)[zle]],
                [f"smuklosc < {P.SMUKLOSC_MIN:g} (za krotkie na taka "
                 f"piersnice - falszywy okrag albo ucieta wysokosc)",
                 f"smuklosc > {P.SMUKLOSC_MAX:g} (za wysokie na taka "
                 f"piersnice - zapewne doliczony czubek sasiada)",
                 f"sciana < {P.SCIANA_MIN:g} (na kazdej wysokosci swieci "
                 f"co innego - to nie jest jeden pien, tylko kepa)",
                 f"srednica ROSNIE ku gorze o ponad "
                 f"{P.MAX_PRZYROST_SREDNICY_CM_NA_M:g} cm/m - pien sie "
                 f"zweza, wiec to nie jest pien"],
                default="nieznana")
            tabela = tabela[~zle].reset_index(drop=True)

            print(f"\n[FILTRY ZDROWEGO ROZSADKU] odrzucono "
                  f"{len(odrzucone)} wierszy")
            print(f"         smuklosc h/d poza {P.SMUKLOSC_MIN:g}"
                  f"-{P.SMUKLOSC_MAX:g}: "
                  f"{int((za_grube.fillna(False) | za_cienkie.fillna(False)).sum())}")
            print(f"         sciana pnia ponizej {P.SCIANA_MIN:g}: "
                  f"{int(nie_sciana.fillna(False).sum())}")
            print(f"         srednica rosnie ku gorze: "
                  f"{int(rozszerza.fillna(False).sum())}")
            for _, r in odrzucone.head(8).iterrows():
                print(f"         drzewo {int(r.id_drzewa):>3}: "
                      f"wys {r.wysokosc_m:5.1f} m, piersnica "
                      f"{zrodlo_dbh.loc[r.name]*100:5.1f} cm, "
                      f"h/d {r.smuklosc_h_d:5.1f}, "
                      f"sciana {r.get('sciana_pnia', float('nan')):.2f}")
            if len(odrzucone) > 8:
                print(f"         ... i {len(odrzucone)-8} wiecej")
            print(f"         Wszystkie w pliku odrzucone_smuklosc.csv - "
                  f"przejrzyj je, nie gina.")
            print(f"         W chmurze .laz ICH PUNKTY ZOSTAJA ze swoimi "
                  f"numerami, zebys mogl je obejrzec w CloudCompare.")

    krok9_zapisz(tabela, punkty, id_drzewa, wysokosc_ng, las,
                 katalog_skanu, nazwa_bazowa)

    if len(odrzucone):
        sc_odrz = katalog_skanu / "odrzucone_smuklosc.csv"
        odrzucone.to_csv(sc_odrz, index=False)
        print(f"         {sc_odrz}")

    # --- zapis lancuchow okregow (model cylindra kazdego pnia) -----------
    # Jeden wiersz = jeden okrag dopasowany na jednej wysokosci. To jest
    # pelny model pnia: ciag okregow jeden nad drugim. Sluzy do ogladania
    # w podglad_drzew.py i do liczenia zbiezystosci.
    if lancuchy_okregow:
        wiersze = []
        for nr, lan in enumerate(lancuchy_okregow, start=1):
            for o in lan:
                wiersze.append({
                    "id_drzewa": nr,
                    "wysokosc_m": round(o[1], 3),
                    "srodek_x": round(o[2], 4),
                    "srodek_y": round(o[3], 4),
                    "promien_m": round(o[4], 4),
                    "srednica_m": round(2 * o[4], 4),
                    "blad_dopasowania_m": round(o[5], 4),
                    "pokrycie_katowe_deg": round(o[6], 1),
                    "pustosc": round(o[7], 3),
                    "liczba_punktow": int(o[8]),
                })
        sciezka = katalog_skanu / f"{nazwa_bazowa}_okregi.csv"
        pd.DataFrame(wiersze).to_csv(sciezka, index=False)
        print(f"         {sciezka}")

    # ==================================================================
    print("\n" + "=" * 66)
    print("TABELA DRZEW")
    print("=" * 66)
    with pd.option_context("display.width", 200, "display.max_columns", 20):
        print(tabela[["id_drzewa", "pozycja_x", "pozycja_y", "dbh_m",
                      "wysokosc_m", "dbh_blad_dopasowania_m",
                      "dbh_pokrycie_katowe_deg", "dbh_uwagi"]]
              .to_string(index=False))

    # --- POWIERZCHNIA POLETKA --------------------------------------------
    # UWAGA, to jest wazniejsze, niz wyglada: od tej liczby zaleza WSZYSTKIE
    # wielkosci "na hektar", czyli te, ktore faktycznie opisuja drzewostan.
    #
    # Pierwsza wersja liczyla pole PROSTOKATA opisanego na chmurze - i mylila
    # sie o 27%, gdy poletko bylo kolem. Kolo o promieniu 20 m ma 1257 m2,
    # a prostokat na nim opisany az 1600 m2. Zageszczenie wychodzilo wtedy
    # 231 drzew/ha zamiast prawdziwych 294.
    #
    # Teraz liczymy pole UCZCIWIE: dzielimy teren na male kwadraty i liczymy
    # te, w ktorych sa jakiekolwiek punkty. Dziala dla kazdego ksztaltu
    # poletka - kola, kwadratu, albo nieregularnego wycinka.
    #
    # Zostaje maly blad na brzegu: komorka lezaca w polowie poza poletkiem
    # liczy sie w calosci. Przy komorce 0.25 m to okolo 2% zawyzenia
    # (sprawdzone na kole o znanym polu: 460 m2 zamiast 452). Mniejsza
    # komorka = dokladniej, ale wolniej.
    krok_pola = 0.25
    kx_p = ((punkty[:, 0] - punkty[:, 0].min()) / krok_pola).astype(np.int64)
    ky_p = ((punkty[:, 1] - punkty[:, 1].min()) / krok_pola).astype(np.int64)
    zajete = len(np.unique(ky_p * (kx_p.max() + 1) + kx_p))
    powierzchnia_ha = zajete * krok_pola ** 2 / 10_000

    prostokat_ha = ((punkty[:, 0].max() - punkty[:, 0].min()) *
                    (punkty[:, 1].max() - punkty[:, 1].min())) / 10_000

    # Podsumowanie skladamy do listy linii, a potem robimy z nia dwie rzeczy:
    # wypisujemy na ekran I zapisujemy do pliku. Wczesniej leciało tylko na
    # ekran i po zamknieciu konsoli przepadalo.
    L = ["-" * 66, "PODSUMOWANIE DRZEWOSTANU", "-" * 66,
         f"  plik zrodlowy        : {args.plik}",
         f"  powierzchnia poletka : {powierzchnia_ha*10_000:.0f} m2 "
         f"({powierzchnia_ha:.4f} ha)  [z zajetych komorek {krok_pola} m]"]
    if prostokat_ha > powierzchnia_ha * 1.05:
        L.append(f"    (prostokat opisany mialby "
                 f"{prostokat_ha*10_000:.0f} m2 - poletko nie jest "
                 f"prostokatem)")
    L += [f"  liczba drzew         : {len(tabela)}",
          f"  zageszczenie         : "
          f"{len(tabela)/powierzchnia_ha:.0f} drzew/ha",
          f"  srednie DBH          : {tabela.dbh_m.mean():.3f} m",
          f"  srednia wysokosc     : {tabela.wysokosc_m.mean():.2f} m",
          f"  pow. przekroju       : "
          f"{tabela.pole_przekroju_m2.sum()/powierzchnia_ha:.2f} m2/ha",
          "-" * 66,
          "",
          "USTAWIENIA, PRZY KTORYCH TO POWSTALO",
          "-" * 66,
          f"  metoda segmentacji   : {args.metoda}",
          f"  metoda wykrywania    : {args.detekcja}",
          f"  sledzenie pnia       : {P.SLEDZENIE_DOL}-{P.SLEDZENIE_GORA} m "
          f"co {P.SLEDZENIE_KROK} m",
          f"  min. plastrow        : {P.SLEDZENIE_MIN_PLASTROW} "
          f"({P.SLEDZENIE_MIN_PLASTROW*P.SLEDZENIE_KROK:.2f} m pnia)",
          f"  prog raportowania DBH: {P.MIN_DBH_RAPORTOWANIA*100:.1f} cm",
          f"  min. pokrycie katowe : {P.DBH_MIN_POKRYCIE_KATOWE:g} stopni",
          f"  filtr sciany pnia    : >= {P.SCIANA_MIN:g}",
          f"  srednica ku gorze    : ma malec "
          f"(odrzut powyzej +{P.MAX_PRZYROST_SREDNICY_CM_NA_M:g} cm/m)",
          f"  filtr smuklosci h/d  : {P.SMUKLOSC_MIN:g} - {P.SMUKLOSC_MAX:g}"
          + (f"   (odrzucil {len(odrzucone)} wierszy)" if len(odrzucone)
             else ""),
          f"  min. pustosc         : {P.DBH_MIN_PUSTOSC}",
          f"  korekta nachylenia   : {P.KORYGUJ_NACHYLENIE}",
          "-" * 66]
    print("\n" + "\n".join(L))

    sciezka_txt = katalog_skanu / "00_PODSUMOWANIE.txt"
    sciezka_txt.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"\n  wszystkie wyniki tego skanu: {katalog_skanu}")


if __name__ == "__main__":
    main()


# ======================================================================
# CO DALEJ - KIEDY TEN KOD PRZESTANIE WYSTARCZAC
# ======================================================================
#
# Ten pipeline radzi sobie z drzewostanem, w ktorym pnie stoja osobno
# i sa widoczne na wysokosci 1-2 m. To bardzo czesta sytuacja i warto
# zaczac wlasnie tutaj. Ale:
#
# 1. GESTY PODSZYT
#    Jesli do 2 m nad gruntem jest las krzakow, KROK 5 zacznie je liczyc
#    jako drzewa. Rozwiazanie: podnies plaster (np. 2.5-3.5 m) i wymagaj,
#    zeby klaster byl PIONOWO ciagly na calej wysokosci plastra.
#
# 2. DRZEWA POCHYLONE I WIELOPNIOWE
#    Zalozenie "pien = pionowy slup" sie lamie. Rozwiazanie: zamiast okregu
#    dopasowywac walec w 3D (os walca moze byc nachylona).
#
# 3. PRZEPLATAJACE SIE KORONY
#    Czesciowo juz rozwiazane: to wlasnie robi --metoda graf (KROK 6b).
#    Na danych testowych poprawila blad wysokosci z RMSE 3.32 m do 1.06 m
#    i skasowala blad systematyczny (+1.83 m -> +0.94 m).
#    Zostajacy +0.94 m to nadal przewieszone galezie sasiadow. Zeby zejsc
#    nizej, trzeba przewidywac dla kazdego punktu WEKTOR do srodka wlasnego
#    drzewa (tzw. offset prediction) - i to jest juz uczenie maszynowe,
#    tak dzialaja TreeLearn, ForAINet i SegmentAnyTree.
#
# 4. GATUNKI
#    Tu i tylko tu potrzebne jest uczenie maszynowe - i dopiero wtedy wraca
#    temat notebooka z PyG. Kolejnosc jest taka: najpierw ten pipeline musi
#    dawac wiarygodne pojedyncze drzewa, potem na ich podstawie uczysz
#    osobny klasyfikator "jedno drzewo -> jeden gatunek". Nie odwrotnie.
# ======================================================================
