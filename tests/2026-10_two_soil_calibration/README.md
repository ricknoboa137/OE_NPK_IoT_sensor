# Two-soil calibration, 25-28 October 2026

Correction factors A and B (x' = A x + B) for N, P and K, solved from the weak-soil
test (`../2026-10-25_weak_soil/`, taken as laboratory sample 59888) and the good-soil
test (`../2026-10-27_good_soil/`, sample 59882), with the sensor value taken in three
windows: matched moisture (40-42 %RH), matched time (2-20 h after insertion) and the
last hour of each test.

| file | content |
| --- | --- |
| `calibrate.py` | computes the medians, A and B, and the comparison figure |
| `calibration_results.json` | the sensor medians, laboratory values, A and B for each window |
| `two_soil_comparison.png` | both soils aligned at insertion |

    C:/Users/User/anaconda3/python.exe tests/2026-10_two_soil_calibration/calibrate.py

The laboratory values are read from the paper repository (set `PAPER_DIR`).
`record_analysis.py` gives the relations between the outputs, the moisture steps, the
change of the readings between steps and the settling after insertion
(`record_results.json`).

The manuscript reports the factors of the last hour of each test, when the two soils
were within 1.2 %RH and 0.2 C of each other, and those of the 40-42 %RH readings for
comparison. `calibration_results.json` also holds the 2-20 h window, not at matched
moisture, where the weak soil was 5.5 %RH wetter and the gains for P and K are negative.
