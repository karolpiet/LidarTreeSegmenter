# LidarTreeSegmenter

Tree detection, segmentation and forest inventory from terrestrial / mobile LiDAR point clouds (TLS, MLS, handheld SLAM scanners).

Drop a `.laz` / `.las` scan of a forest plot onto the program and you get, for every tree: position, DBH (diameter at 1.3 m), height, species group, stem / branches / foliage split and timber volume, plus a plot-level summary (N/ha, basal area, Dg, Lorey's height, V/ha), an Excel report, a GeoPackage with a ready QGIS project, per-tree images and an interactive 3D view in the browser.

No machine learning model to download and no GPU needed: the pipeline is geometric (circle and cylinder fitting, neighbourhood graphs) plus a small random forest trained on each scan by itself.


## Requirements

- Windows 10/11 (the `.bat` launchers). The Python scripts also run on Linux and macOS from the command line.
- Python 3.10 or newer from [python.org](https://www.python.org/downloads/). Tick **"Add Python to PATH"** during installation.
- About 8 GB of free RAM for a large scan (40 million points or more).

Python libraries (installed by `INSTALL_ONCE.bat`, or by hand):

```
python -m pip install -r requirements.txt
```

## Documentation

- [User manual](docs/user_manual.pdf): installation, first scan, results, review, overnight queue, GPS matching, QGIS, FAQ.
- [How it works](docs/how_it_works.pdf): every stage and algorithm, parameters, accuracy and limitations.

## Quick start

1. **Once:** double-click `INSTALL_ONCE.bat`. It installs the libraries.
2. **Every time:** double-click `LidarTreeSegmenter.bat`, choose a scan (`.laz` or `.las`) and click **Start**. You can also drop a scan onto `LidarTreeSegmenter.bat` and processing starts by itself.
3. The window shows the progress of each step, the number of trees, the share of stem, branches and foliage, and volume per hectare. The **Live preview** tab shows the cloud while it is being processed. At the end, buttons open the results folder, tree images, the Excel report and the 3D view.

Before **Start**, choose two things (the window remembers them for each scan):

- **Stand class:** `young` (DBH about 8–20 cm), `mature` (thicker) or `automatic` (picked from the median DBH). The class sets the stem diameters searched for, the height below which a thick object counts as a shrub, and the understory range. The numbers are in `klasy_drzewostanu.csv` and you can change them.
- **Species:** `recognise from shape`, `spruce only` or `beech only`. If you know the plot has one species, choose it: shape-based recognition in dense stands can confuse spruce and beech because crowns overlap.

Without the window: drop a scan onto `DRAG_SCAN_HERE.bat` (console version).

Polish version: `LidarTreeSegmenter_PL.bat`, `PRZECIAGNIJ_TU_SKAN.bat`, `ZAINSTALUJ_RAZ.bat`. The whole run (window, log, Excel, GeoPackage, images, 3D view) is in one language, chosen by the environment variable `LTS_LANG` (`en` by default, `pl` for Polish).

### Try it without your own data

A synthetic test plot (30 × 30 m, 18 trees with known DBH and height) can be generated:

```
python tree_segmenter_tool\90_make_test_forest.py
```

It writes `tree_segmenter_tool\data\las_testowy.laz` and `las_testowy_prawda.csv` (the true values). Drop the `.laz` onto `LidarTreeSegmenter.bat`.

## Pipeline

| Step | Script | What it does |
|---|---|---|
| 1 | `program/05_wykryj_drzewa.py` (uses `tree_segmenter_tool/02_detect_trees.py`) | noise removal, ground and DTM, height normalisation, stem detection in slices 0.5–6 m and a second pass higher up (2.5–8.5 m) to find stems hidden in dense understory, point-to-tree segmentation, DBH and height |
| 2 | `program/10_pien_galezie_liscie.py` | stem tracking every 20 cm up into the crown, stem / branches / foliage / understory classification, species group from tree shape, per-tree images |
| 3 | `program/30_raport.py` | stem checks (cylinder test, shrub and snag detection), volume, Excel report, text summary, GeoPackage, QGIS project, field-measurement matching |
| 4 | `program/40_widok_3d.py` | interactive 3D view (single HTML file, works offline) |

The GUI is `program/LidarTreeSegmenter_okno.py`.

### Quality checks that remove false trees

- **Cylinder check** (`program/lts_walec.py`): for each tree, all scan points within 0.7 m of the stem at 0.6–3.0 m above ground are tested for a real stem: circles fitted in 25 cm slices must stack into one cylinder (nearly vertical axis, constant or slowly tapering radius, bark points around the circumference and an empty centre). If the scanner trajectory is known, the visible part of the circumference is compared with the sides the scanner passed. Result: `stem` (confirmed), `no stem` (removed from totals) or `uncertain` (kept, with a note). Written to `03_TABELE/<scan>_kontrola_walca.csv`.
- **Shrubs instead of trees:** a stem cross-section is hollow (points only on the bark); a shrub has points inside. Objects that are full inside and lower than the stand-class limit (5 m young, 10 m mature) are marked as **shrubs** and excluded from totals.
- **Too thick for its height:** a low, very thick object is either a **snag** (hollow inside: kept, volume = measured stem volume) or a stump / shrub cluster (excluded).
- **DBH disagreement:** steps 1 and 2 measure DBH independently. When they differ by more than 30 %, the value that fits the stand's height–diameter curve is used, and the choice is noted in the report.
- **Dense understory:** when the lower stem is hidden, the stem is traced from above and the hidden part is reconstructed from the stem taper (marked as "reconstructed").

## Manual tree review (for final results)

1. After processing, click **Review trees**. The 3D view opens in review mode.
2. Trees are shown one by one, suspicious ones first (shrubs, snags, uncertain, no DBH).
3. Keys: **1** tree OK, **2** shrub, **3** snag, **4** spruce, **5** beech, **→** skip, **←** back.
4. Decisions are saved in the browser as you go. At the end click **Save review** and save `<scan>_sprawdzenie.csv` in `wyniki\<scan>\01_RAPORT`.
5. Click **Recalculate report** in the window. Only the report and 3D view are recomputed (seconds).

Your decisions override the program's. The review file is a plain CSV (`nr;decyzja;gatunek`); English values (`tree`, `shrub`, `snag`, `spruce`, `beech`) are accepted.

## Overnight queue (many scans)

Click **Overnight queue…** (or drop several scans or a folder onto `LidarTreeSegmenter.bat`). Add files or folders, set stand class and species per scan, choose whether to skip steps already computed, and what to do at the end (nothing, sleep, shut down). Errors in one scan do not stop the others. A summary `wyniki\KOLEJKA_<date>_<time>.xlsx` is written after each scan, one row per plot.

## Field measurement (matching trees measured with GPS)

If you measured a few trees in the field (for example 5 trees with a Garmin), the program finds them in the scan, rotates and shifts the scan into field coordinates and compares DBH.

1. Copy `TEMPLATE_field_measurement.csv` as `<scan>_field.csv` and fill in `nr;lat;lon;dbh_cm;species;height_m` (species and height are optional). Coordinates can be decimal degrees or Garmin format (`N49 36.740`), or `x;y;epsg`. A Garmin `.gpx` file (waypoint name = tree number) also works.
2. Put the file in `wyniki\<scan>\01_RAPORT` or next to the scan and click **Recalculate report**.
3. You get a **Field measurement** sheet in Excel and `01_RAPORT\<scan>_georef.gpkg` in UTM (or another EPSG: `python program\30_raport.py wyniki\<scan> --epsg 2180`).

Tips: average the GPS position at each tree, choose trees 6–14 m from the plot centre in different directions, with clearly different DBH.

## Scanner trajectory, terrain and fly-through

- **Trajectory** (optional) is found automatically next to the scan (file names containing `Trajectory`, `traj`, `path`, `odom`, `pose`, `track`), or chosen in the window. Formats: `.las`, `.laz`, `.ply`, and text exports (GeoSLAM, Emesent, ROS, TUM, KITTI, plain x y z). It adds visibility information to images and the report, a `sciezka_skanera` layer and a scanner fly-through animation in the 3D view.
- **Terrain model** (0.25 m grid): elevation, slope, hillshade and contours in the GeoPackage; relief, mean slope and aspect in the report.
- **Species from scanner tags:** if trees were tagged with species codes during scanning (`markPoint.csv`), the tags are assigned to the nearest stem.

## Output

All results of one scan go to `wyniki\<scan_name>\`:

```
wyniki\<scan>\
  01_RAPORT\         <scan>_REPORT.xlsx, 00_SUMMARY.txt, <scan>.gpkg, <scan>.qgs, <scan>_species.csv
  02_CHMURY\         <scan>_segmenty.laz (tree id per point), <scan>_czesci.laz (stem/branches/foliage)
  03_TABELE\         all CSV tables and settings
  04_OBRAZY_DRZEW\   drzewo_001.png ... one image per tree
  05_DZIENNIK\       processing log
  06_WIDOK_3D\       <scan>_cloud_3d.html - 3D view, double-click to open in a browser
```

- **Excel report:** summary (N/ha, DBH, Dg, H, Lorey's height, G/ha, V/ha, DBH distribution), one row per tree, settings and explanations.
- **GeoPackage + QGIS project:** trees with species, DBH, height and volume, stem cross-sections and points at 1.3 m and 3 m, shrubs, terrain layers, trajectory. Double-click the `.qgs` to open everything with styles.
- **3D view:** colour by tree, part or height; click a tree for its data. The cloud is thinned to 600 k points; for more: `python program\40_widok_3d.py wyniki\<scan> --punktow 1500000`.
- **Point clouds:** `_czesci.laz` has a field `czesc` (1 stem, 2 branches, 3 foliage, 4 understory) that CloudCompare can colour by.

Folder and file names inside `wyniki` are Polish in both language versions (`wyniki` = results, `RAPORT` = report, `CHMURY` = clouds, `TABELE` = tables, `OBRAZY_DRZEW` = tree images, `DZIENNIK` = log, `WIDOK_3D` = 3D view).

## Volume and species

Volume is merchantable timber volume from `tablice_miazszosci.csv`: by default V = g·h·f with approximate form factors (spruce 0.47, beech 0.51, coniferous 0.45, broadleaved 0.50, unspecified 0.47). Replace them with regional tables; power formulas V = a·d^b·h^c are also supported (see the file header).

To set species by hand, edit the column `gatunek_reczny` in `wyniki\<scan>\01_RAPORT\<scan>_species.csv` and recalculate the report:

```
python program\30_raport.py wyniki\<scan>
python program\30_raport.py wyniki\<scan> --gatunek spruce    (whole plot is one species)
```

Priority: manual review > species CSV > scanner tags > whole-plot species > recognition from shape.

## Comparing segmentation methods (optional)

`program/21_ujednolic_wynik.py` converts the output of any segmentation tool (field `treeID_pred`, `final_segs`, `PredInstance`, ...) to a common format, and `program/20_porownaj_segmentacje.py` ranks methods against a manually segmented reference (precision, recall, F1 at IoU ≥ 0.5). The reference file paths are set in `WZORCE` at the top of `20_porownaj_segmentacje.py`.

## Repository layout

```
LidarTreeSegmenter.bat          GUI (English)            LidarTreeSegmenter_PL.bat   GUI (Polish)
DRAG_SCAN_HERE.bat              console version          PRZECIAGNIJ_TU_SKAN.bat     console (Polish)
INSTALL_ONCE.bat                install libraries        ZAINSTALUJ_RAZ.bat          install (Polish)
klasy_drzewostanu.csv           stand class settings
tablice_miazszosci.csv          volume formulas
TEMPLATE_field_measurement.csv  field measurement template (SZABLON_pomiar.csv = Polish)
program/                        the program
tree_segmenter_tool/            step 1 tree detection + synthetic test plot generator
docs/user_manual.pdf            user manual, step by step (English)
docs/how_it_works.pdf           all stages, algorithms, parameters and accuracy (English)
docs/src/                       HTML sources and figures of both PDFs
docs/CZYTAJ_MNIE_PL.md          detailed guide in Polish
docs/KURS_PYTHONA/              Python course built around the program (Polish)
```

Code comments and internal names are in Polish; all user-facing text has an English version.

## License

MIT, see [LICENSE](LICENSE). The bundled three.js and OrbitControls (`program/biblioteki_js`) are also MIT-licensed.
