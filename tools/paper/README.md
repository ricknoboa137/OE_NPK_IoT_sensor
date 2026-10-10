# Manuscript analysis scripts

These produced and verify the figures quoted in the Agriculture manuscript. They
read the logged sensor readings from `DB_01.db` in this repository and the
manuscript, laboratory database and calibration workbook from the paper
repository, which is private and kept separately.

Point them at a checkout of the paper:

    set PAPER_DIR=C:/path/to/Agriculture-4351955

| script | what it does |
| --- | --- |
| `audit_paper_numbers.py` | recomputes every figure quoted in the manuscript from the raw sources and checks it appears in the .tex |
| `paper_analysis.py` | the characterisation behind the nutrient-channel section: collinearity, the zero floor, moisture sensitivity, laboratory correlations |
| `solve_paper_cal.py` | the two-soil calibration: means per soil, fitted A and B, direction against the laboratory |
| `check_manuscript_tex.py` | structural checks on the .tex: \hl spans soul cannot typeset, brace balance, cross-references, table column counts |
| `make_paper_revision.py` | historical: built the first revision from the original .tex. Do not re-run; the revised .tex has been edited directly since. |

Run with the Anaconda interpreter:

    C:/Users/User/anaconda3/python.exe tools/paper/audit_paper_numbers.py

## Added for the satellite case study

| script | what it does |
| --- | --- |
| `ndmi_station_analysis.py` | field-mean Sentinel-2 NDMI against the Csolnok station soil moisture, the within-field spread of NDMI, and the figure `Pic/NDMI_station.png`. Needs rasterio and geopandas: run it with the `tf210` environment. Writes `ndmi_station_results.json`, which the audit reads. |
| `insertion_analysis.py` | from the two-soil campaign: the nitrogen output against the moisture output across insertions in one soil, and how long a reading takes to settle after an insertion (5 s log). |

The forecasting metrics quoted in the manuscript come from the WREN project
(`paper/figures/metrics.txt`); set `WREN_DIR` if it is not in `Documents/GitHub/WREN`.
`check_manuscript_tex.py` now also reports highlighted spans that cross a blank line or are
nested, the two faults that stop the build.
