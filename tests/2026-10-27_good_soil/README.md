# Good soil, from 27 October 2026

The probe was moved from the weak soil to the good soil and left in place, with the
moisture to be kept at about 40 %, to follow the NPK readings over time.

## Record of the change (local time, CET = UTC+1)

| time | event |
| --- | --- |
| 13:20:04 | last reading in the weak soil (end of `../2026-10-25_weak_soil/`) |
| 13:20:09 | probe removed: moisture falls to about 18 %, N, P and K to 0 |
| 13:23:04 | probe inserted in the good soil: moisture rises to 36 %, P and K start reading |
| 13:23:54 | first reading with nitrogen above zero (start of the in-soil record used by the plot) |

The times are taken from the log (UTC 12:20:04, 12:20:09, 12:23:04 and 12:23:54).

| file | content |
| --- | --- |
| `readings.csv` | the readings of the test, copied from the live database (UTC timestamps) |
| `plot_test.py` | draws the six channels; moisture is also shown as a 10-reading moving average |
| `good_soil_test.png` | the figure |

Re-export the readings and redraw while the test runs:

    C:/Users/User/anaconda3/python.exe tests/2026-10-27_good_soil/plot_test.py --refresh

The test ended on 28 October 2026 at 09:45:02 local time (08:45:02 UTC), when the laptop
was disconnected from the Node-RED flow.

Used in the manuscript (`Pic/good_soil_test.png`).
