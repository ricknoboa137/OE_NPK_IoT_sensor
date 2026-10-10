"""Time series of the six channels of the module, drawn from the logged readings.

Replaces the dashboard screenshot: the same six panels (temperature, moisture
and pH; nitrogen, phosphorus and potassium), but computed from
database/sensor_log.csv.gz, so the figure can be regenerated and checked.

    C:/Users/User/anaconda3/python.exe tools/paper/make_timeseries_figure.py
    C:/Users/User/anaconda3/python.exe tools/paper/make_timeseries_figure.py 2026-08-28 2026-09-09 preview.png

Times are UTC, as in the log (local time was UTC+2).
Only readings taken with the electrodes in soil are drawn (moisture between 15
and 60 %RH and a nitrogen output above zero, the definition used throughout the
manuscript); the line is broken wherever the record is interrupted.
"""
import sys, datetime as dt
import numpy as np
import paper_data

START, END = "2026-09-01", "2026-09-08"      # UTC dates, END exclusive: the window analysed in the manuscript
LOCAL = dt.timedelta(hours=0)                  # the axis is in UTC, like the log
GAP_S = 600                                    # a break in the line after ten minutes without readings
MEDIAN_S = 300                                 # readings are condensed to five-minute medians

PANELS = (("temperature", "Temperature (°C)"), ("N", "Nitrogen output (mg/kg)"),
          ("humidity", "Moisture (%RH)"), ("P", "Phosphorus output (mg/kg)"),
          ("PH", "pH"), ("K", "Potassium output (mg/kg)"))


def load(start, end):
    con = paper_data.log_connection()
    t0 = (dt.datetime.fromisoformat(start) - LOCAL).replace(tzinfo=dt.timezone.utc).timestamp()
    t1 = (dt.datetime.fromisoformat(end) - LOCAL).replace(tzinfo=dt.timezone.utc).timestamp()
    rows = con.execute(
        "select timestamp, temperature, humidity, PH, N, P, K from NPKv1 "
        "where timestamp >= ? and timestamp < ? and humidity between 15 and 60 and N > 0 "
        "and P is not null and K is not null "
        "order by timestamp", (t0, t1)).fetchall()
    a = np.array(rows, dtype="float64")
    return dict(t=a[:, 0], temperature=a[:, 1], humidity=a[:, 2], PH=a[:, 3], N=a[:, 4], P=a[:, 5], K=a[:, 6])


def condense(d):
    """Five-minute medians, with a NaN row wherever the record is interrupted."""
    bins = (d["t"] // MEDIAN_S).astype("int64")
    keys = np.unique(bins)
    out = {k: [] for k in d}
    prev_end = None
    for key in keys:
        m = bins == key
        if prev_end is not None and d["t"][m][0] - prev_end > GAP_S:
            for k in out:
                out[k].append(np.nan if k != "t" else (prev_end + d["t"][m][0]) / 2)
        for k in d:
            out[k].append(np.median(d[k][m]))
        prev_end = d["t"][m][-1]
    return {k: np.array(v) for k, v in out.items()}


def figure(start, end, path, marks=()):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    raw = load(start, end)
    d = condense(raw)
    x = [dt.datetime.fromtimestamp(t, dt.timezone.utc).replace(tzinfo=None) + LOCAL for t in d["t"]]

    INK, MUTED, GRID, BLUE = "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.linewidth": 0.6})
    fig, axes = plt.subplots(3, 2, figsize=(7.4, 5.6), dpi=300, sharex=True)
    for ax, (key, label) in zip(axes.ravel(), PANELS):
        ax.plot(x, d[key], color=BLUE, linewidth=0.9)
        ax.set_title(label, loc="left", fontsize=8, color=INK)
        ax.grid(True, color=GRID, linewidth=0.5)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for when, text in marks:
            ax.axvline(dt.datetime.fromisoformat(when), color=MUTED, linewidth=0.7, linestyle=(0, (3, 2)))
        ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    for when, text in marks:
        axes[0, 0].annotate(text, (dt.datetime.fromisoformat(when), 1.0), xycoords=("data", "axes fraction"),
                            xytext=(3, -2), textcoords="offset points", va="top", fontsize=7, color=MUTED)
    axes[0, 0].set_xlim(dt.datetime.fromisoformat(start), dt.datetime.fromisoformat(end))
    fig.tight_layout(h_pad=1.2, w_pad=2.0)
    fig.savefig(path, dpi=300, facecolor="white", metadata={"Software": None})
    print(f"{len(raw['t'])} in-soil readings from {start} to {end} (UTC) -> {path}")


if __name__ == "__main__":
    if len(sys.argv) == 4:
        figure(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        figure(START, END, paper_data.PAPER / "Pic" / "sensor_timeseries.png",
               marks=(("2026-09-05 12:43", "two-soil campaign"),))
