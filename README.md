# HaBB DiveSync

**A Python tool for synchronising underwater video, USBL and CTD data for benthic habitat mapping**

Developed at the [HaBB Lab — Habitat and Benthic Biodiversity](https://www.kaust.edu.sa), Red Sea Research Center, KAUST.

---

## Overview

HaBB DiveSync is a desktop GUI tool for marine scientists and geologists doing habitat mapping with ROVs, submersibles or towed camera systems. It synchronises video recordings with USBL positioning files and CTD sensor data, and extracts geotagged frames ready for use in ArcGIS, QGIS or image annotation software.

**Typical use case:** you have a dive video, a USBL tracklog, and a CTD cast. The camera clock may be wrong by hours, and the CTD clock by minutes. HaBB DiveSync lets you correct both offsets interactively, then batch-extract frames with full position and environmental metadata embedded in a companion CSV (and optionally a shapefile).

---

## Features

- **Robust video timestamp detection** — four cascading strategies (sidecar .txt, pymediainfo, MediaInfo CLI, built-in ISOBMFF binary parser) with colour-coded reliability indicator
- **USBL mapping** — supports NMEA, decimal degrees, degrees-minutes, degrees-minutes-seconds, and UTM coordinate formats; timestamp in unified, split or unix epoch columns
- **CTD synchronisation in two modes**
  - *By time* — for CTDs mounted on the ROV sharing a clock; interactive depth-vs-time overlay with drag alignment and robust auto-align (full profile cross-correlation)
  - *By depth* — for independent CTD casts; graphical downcast/upcast selector
- **Touchdown sync** — click the USBL track at the touchdown moment, move the video slider to the matching frame, one button computes the video-to-USBL offset
- **Frame extraction** — configurable interval, PNG/JPEG/TIFF, quality filters (blur, dark, bright), optional text overlay with depth, time and coordinates
- **GIS-ready output** — CSV with all coordinates and CTD parameters per frame; optional shapefile export (requires geopandas)
- **Bilingual UI** — English and Italian interface

---

## Installation

### Option 1 — Standalone Windows executable (recommended for non-programmers)

Download `ROV_Sync_Tool.exe` from the [Releases page](../../releases/latest).
No Python or any other software required. Just double-click and run.

> The executable bundles Python and all dependencies. It is self-contained.

### Option 2 — Run from Python source

Requires **Python 3.8+**.

```bash
git clone https://github.com/Geothorin/habb-divesync.git
cd habb-divesync
pip install -r requirements.txt
python rov_sync_tool.py
```

Or, on Windows, double-click `install.bat` to install dependencies automatically, then `avvia_rov_Tool.bat` to launch.

#### Optional dependencies

| Package | Effect if missing |
|---|---|
| `pymediainfo` | Falls back to MediaInfo CLI or built-in binary parser for timestamp detection |
| `MediaInfo CLI` | Falls back to built-in parser (install from [mediaarea.net](https://mediaarea.net)) |
| `geopandas` + `shapely` | Shapefile export disabled |
| OpenCV with CUDA | Standard CPU decoding used instead of GPU-accelerated |

---

## Quick start

1. Load video, USBL file and CTD file in **Tab 1**.
2. Detect the video start timestamp and pick the most reliable candidate.
3. Map USBL columns (lat, lon, depth, time) in **Tab 2** and press *Validate USBL*.
4. Map CTD columns and sync mode in **Tab 3** and press *Validate CTD*.
5. Add any fixed metadata columns (dive name, ROV code, site...) in **Tab 4**.
6. In **Tab 5**:
   - Move the video slider to the ROV touchdown frame; click the same moment on the USBL plot; press *Synchronise*.
   - Press *Auto-align (depth match)* to align the CTD clock, then fine-tune by dragging the red CTD curve, then press *Apply*.
   - Set extraction range (From / To, editable in seconds or UTC).
   - Press *Start extraction*.
7. Output folder: PNG/JPG/TIFF frames + `output.csv` (+ optional shapefile).

Full documentation: see `HaBB_DiveSync_Manual_EN.pdf` (English) and `HaBB_DiveSync_Manual_IT.pdf` (Italian) in this repository.

---

## Repository structure

```
habb-divesync/
├── rov_sync_tool.py          # Main application
├── lang.py                   # UI string translations (EN/IT)
├── requirements.txt          # Python dependencies
├── install.bat               # Windows: installs dependencies
├── Logos/                    # HaBB Lab logo assets
├── HaBB_DiveSync_Manual_EN.pdf   # English user manual
├── HaBB_DiveSync_Manual_IT.pdf   # Italian user manual
├── LICENSE
├── CITATION.cff
└── README.md
```

---

## Citing this software

If you use HaBB DiveSync in your research, please cite it using the metadata in `CITATION.cff` or the reference below.

> Marchese, F., Benzoni, F. (2026). *HaBB DiveSync: a Python tool for synchronising underwater video, USBL and CTD data for habitat mapping* (v1.0). Zenodo. https://doi.org/10.5281/zenodo.21237716

A formatted citation is also available directly from the GitHub sidebar ("Cite this repository") once the DOI is registered on Zenodo.

---

## License

This project is licensed under the **MIT License** — see `LICENSE` for details.

---

## Authors

- **Fabio Marchese** — BESE Division, King Abdullah University of Science and Technology (KAUST)
- **Francesca Benzoni** — Marine Science Program, BESE Division, King Abdullah University of Science and Technology (KAUST)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21237716.svg)](https://doi.org/10.5281/zenodo.21237716)
