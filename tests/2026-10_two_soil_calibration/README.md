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
Result: A and B change sign with the window chosen, because the weak-soil readings
drifted throughout the test; they are not used in the firmware.
