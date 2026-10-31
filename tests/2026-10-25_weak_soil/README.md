# Weak soil, from 25 October 2026

The probe was inserted in the weak soil on the evening of 25 October 2026 and left in
place, with the moisture kept at about 40 % by a constant drop method (checking and adjusting the drops caused the moisture steps), to follow the NPK readings over time. The
test ended on 27 October 2026 at 13:20:04 local time (12:20:04 UTC), when the probe
was removed and moved to the good soil (see `../2026-10-27_good_soil/`).

| file | content |
| --- | --- |
| `readings.csv` | the readings of the test, copied from the live database (UTC timestamps) |
| `plot_test.py` | draws the six channels; moisture is also shown as a 10-reading moving average |
| `weak_soil_test.png` | the figure |

Rebuild the figure from the saved readings (the export is limited to the test period):

    C:/Users/User/anaconda3/python.exe tests/2026-10-25_weak_soil/plot_test.py
    C:/Users/User/anaconda3/python.exe tests/2026-10-25_weak_soil/plot_test.py --refresh

Used in the manuscript (`Pic/weak_soil_test.png`).
