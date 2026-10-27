"""Weak-soil test started on the evening of 25 October 2026: the probe stays in the
weak soil, kept at about 40 % moisture, to follow the NPK readings over time.

    C:/Users/User/anaconda3/python.exe tests/2026-10-25_weak_soil/plot_test.py            # from the saved readings
    C:/Users/User/anaconda3/python.exe tests/2026-10-25_weak_soil/plot_test.py --refresh  # re-export from the live database first

--refresh copies the test readings out of the live Node-RED database (DB_01.db,
not versioned) into readings.csv beside this script, so the figure can always be
rebuilt from the repository. Times in the log are UTC; the plot uses local time
(CET, UTC+1, after the change from summer time on 25 October 2026).
"""
import argparse, csv, sqlite3, pathlib, datetime as dt
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
DB = REPO / "DB_01.db"
READINGS = HERE / "readings.csv"
FIGURE = HERE / "weak_soil_test.png"

TEST_FROM_UTC = "2026-10-25 17:00"    # the probe was inserted shortly after this
TEST_TO_UTC = "2026-10-27 12:19:29"   # last reading in the weak soil; the test ended here
LOCAL = dt.timedelta(hours=1)        # CET
WINDOW = 10                          # moisture moving average, in readings (5 s apart)
TARGET = 40.0                        # %RH, the moisture the test aims to hold
COLUMNS = ("timestamp", "humidity", "temperature", "PH", "N", "P", "K")


def refresh():
    """Copy the in-soil readings of the test out of the live database."""
    con = sqlite3.connect(DB)
    t0 = con.execute(
        "select min(timestamp) from NPKv1 where timestamp >= strftime('%s', ?) "
        "and humidity between 15 and 60 and N > 0", (TEST_FROM_UTC,)).fetchone()[0]
    rows = con.execute(f"select {', '.join(COLUMNS)} from NPKv1 where timestamp >= ? "
                       "and timestamp <= strftime('%s', ?) order by timestamp", (t0, TEST_TO_UTC)).fetchall()
    with open(READINGS, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(f"{len(rows)} readings exported, from {dt.datetime.utcfromtimestamp(rows[0][0])} "
          f"to {dt.datetime.utcfromtimestamp(rows[-1][0])} UTC")


def load():
    with open(READINGS, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f)]
    return {k: np.array([float(r[k]) if r[k] != "" else np.nan for r in rows]) for k in COLUMNS}


def moving_average(x, n):
    """Mean of the last n readings (the first n - 1 points average what is available)."""
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.empty_like(x)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    out[:n - 1] = c[1:n] / np.arange(1, n)
    return out


def summary(d, m_avg):
    t = d["timestamp"]
    hours = (t[-1] - t[0]) / 3600
    print(f"{len(t)} readings over {hours:.1f} h, "
          f"{(dt.datetime.utcfromtimestamp(t[0]) + LOCAL):%d %b %H:%M} to "
          f"{(dt.datetime.utcfromtimestamp(t[-1]) + LOCAL):%d %b %H:%M} local time")
    settled = t >= t[0] + 3600          # after the first hour
    print(f"moisture ({WINDOW}-reading average), after the first hour: mean {m_avg[settled].mean():.1f} %RH, "
          f"range {m_avg[settled].min():.1f}-{m_avg[settled].max():.1f} %RH")
    for k, unit in (("temperature", "C"), ("PH", ""), ("N", "mg/kg"), ("P", "mg/kg"), ("K", "mg/kg")):
        v = d[k][settled]
        print(f"{k:12} after the first hour: {v.min():6.1f} to {v.max():6.1f} {unit}; last hour mean "
              f"{d[k][t >= t[-1] - 3600].mean():6.1f}")


def figure(d, m_avg):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    x = [dt.datetime.utcfromtimestamp(s) + LOCAL for s in d["timestamp"]]
    INK, MUTED, GRID, BLUE, LIGHT = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6", "#a9c8ef"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.linewidth": 0.6})
    fig, axes = plt.subplots(3, 2, figsize=(7.4, 5.6), dpi=200, sharex=True)
    panels = (("humidity", "Moisture (%RH)"), ("N", "Nitrogen output (mg/kg)"),
              ("temperature", "Temperature (°C)"), ("P", "Phosphorus output (mg/kg)"),
              ("PH", "pH"), ("K", "Potassium output (mg/kg)"))
    for ax, (key, label) in zip(axes.ravel(), panels):
        if key == "humidity":
            ax.plot(x, d[key], color=LIGHT, linewidth=0.5, label="readings")
            ax.plot(x, m_avg, color=BLUE, linewidth=1.1, label=f"{WINDOW}-reading average")
            ax.axhline(TARGET, color=MUTED, linewidth=0.8, linestyle=(0, (4, 2)), label=f"target {TARGET:.0f} %RH")
            ax.legend(frameon=False, fontsize=7, loc="lower right", handlelength=1.6)
        else:
            ax.plot(x, d[key], color=BLUE, linewidth=0.9)
        ax.set_title(label, loc="left", fontsize=8, color=INK)
        ax.grid(True, color=GRID, linewidth=0.5)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    for ax in axes[-1]:
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=(0, 12)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b\n%H:%M"))
        ax.set_xlabel("Local time (CET)", color=MUTED)
    fig.suptitle("Weak soil, probe left in place from 25 to 27 October 2026", x=0.01, ha="left", fontsize=9, color=INK)
    fig.tight_layout(h_pad=1.0, w_pad=2.0)
    fig.savefig(FIGURE, facecolor="white", metadata={"Software": None})
    print(f"figure written: {FIGURE}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-export the readings from the live database")
    args = ap.parse_args()
    if args.refresh or not READINGS.exists():
        refresh()
    d = load()
    m_avg = moving_average(d["humidity"], WINDOW)
    summary(d, m_avg)
    figure(d, m_avg)
