"""Satellite NDMI against the one ground record, Csolnok field: the numbers of
the case study and the figure Pic/NDMI_station.png.

Reads only the versioned dataset in the paper repository (see paper_data.py);
build_ndmi_dataset.py records how that dataset was derived from the raw files.

    C:/Users/User/anaconda3/python.exe tools/paper/ndmi_station_analysis.py
"""
import json, math, pathlib, statistics as st, datetime as dt
import numpy as np
import pandas as pd
from scipy import stats
import paper_data as pd_


def compute():
    """Return every figure quoted in the manuscript, plus the series for the plot."""
    z = np.load(pd_.NDMI_STACK)
    ndmi = z["ndmi"].astype("float64")
    dates = [dt.date.fromisoformat(d) for d in z["date"]]
    meta = json.loads(pd_.FIELD_META.read_text(encoding="utf-8"))

    out = {"field_ha": meta["field_ha"], "pixel_m": meta["pixel_m"], "pixel_m2": meta["pixel_m2"],
           "stations": meta["stations_in_network_file"],
           "station_to_boundary_m": meta["station_to_boundary_m"],
           "station_to_centroid_m": meta["station_to_centroid_m"],
           "station_inside": meta["station_inside_field"]}
    out["scenes"] = len(dates)
    out["s2a"] = int((z["satellite"] == "S2A").sum())
    out["s2b"] = int((z["satellite"] == "S2B").sum())
    out["l1c"] = int((z["level"] == "L1C").sum())
    out["l2a"] = int((z["level"] == "L2A").sum())

    order = np.argsort(np.array([d.toordinal() for d in dates]), kind="stable")
    by_date = {}
    for i in order:
        by_date.setdefault(dates[i], ndmi[i])
    days = sorted(by_date)
    out["first"], out["last"] = days[0], days[-1]
    out["gap_median_days"] = st.median([(b - a).days for a, b in zip(days, days[1:])])
    out["field_pixels"] = int(st.median([int(np.isfinite(a).sum()) for a in by_date.values()]))

    series = pd.DataFrame({
        "date": days,
        "ndmi_mean": [np.nanmean(by_date[d]) for d in days],
        "ndmi_sd": [np.nanstd(by_date[d]) for d in days],
        "p05": [np.nanpercentile(by_date[d], 5) for d in days],
        "p95": [np.nanpercentile(by_date[d], 95) for d in days],
    })
    out["within_sd_median"] = float(series.ndmi_sd.median())
    out["within_sd_q1"] = float(series.ndmi_sd.quantile(.25))
    out["within_sd_q3"] = float(series.ndmi_sd.quantile(.75))
    out["within_spread_median"] = float((series.p95 - series.p05).median())
    out["temporal_sd"] = float(series.ndmi_mean.std(ddof=0))

    daily = pd.read_csv(pd_.STATION_DAILY)
    daily["date"] = [dt.date.fromisoformat(d) for d in daily.date]
    daily = daily.set_index("date")[["soil_moisture"]]
    j = series.join(daily, on="date").dropna(subset=["soil_moisture"]).copy()
    j["season"] = [4 <= d.month <= 9 for d in j.date]

    def corr(frame):
        r, p = stats.pearsonr(frame.ndmi_mean, frame.soil_moisture)
        lo, hi = np.tanh(np.arctanh(r) + np.array([-1.96, 1.96]) / math.sqrt(len(frame) - 3))
        return dict(r=float(r), r2=float(r * r), p=float(p), lo=float(lo), hi=float(hi), n=len(frame))

    out["all"] = corr(j)
    out["season"] = corr(j[j.season])
    out["offseason"] = corr(j[~j.season])
    return out, series, j


def report(o):
    print("FIELD AND SCENES")
    print(f"  field area {o['field_ha']:.2f} ha ; {o['field_pixels']} in-field pixels of "
          f"{o['pixel_m']:.0f} m ({o['pixel_m2']:.0f} m2)")
    print(f"  {o['scenes']} scenes, Sentinel-2A {o['s2a']} + Sentinel-2B {o['s2b']} ; "
          f"L1C {o['l1c']} + L2A {o['l2a']} ; {o['first']} to {o['last']} ; "
          f"median {o['gap_median_days']:.0f} days between scenes")
    print("WITHIN-FIELD VARIABILITY")
    print(f"  spatial SD per date: median {o['within_sd_median']:.3f} "
          f"(IQR {o['within_sd_q1']:.3f}-{o['within_sd_q3']:.3f}) ; "
          f"5th-95th percentile spread: median {o['within_spread_median']:.3f}")
    print(f"  SD over time of the field mean: {o['temporal_sd']:.3f}")
    print("STATION")
    print(f"  {o['stations']} stations in the network file ; the station is "
          f"{o['station_to_boundary_m']:.0f} m from the field boundary and "
          f"{o['station_to_centroid_m']:.0f} m from its centroid ; inside the field: {o['station_inside']}")
    print("FIELD-MEAN NDMI AGAINST STATION SOIL MOISTURE, SAME DAY")
    for key, name in (("all", "all dates"), ("season", "April-September"), ("offseason", "October-March")):
        c = o[key]
        print(f"  {name:16} n={c['n']:3d}  r={c['r']:+.3f} (95% CI {c['lo']:+.3f} to {c['hi']:+.3f})  "
              f"r2={c['r2']:.3f}  p={c['p']:.2g}")


def figure(o, series, j, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
    BLUE, ORANGE = "#2a78d6", "#eb6834"          # a pair checked for color-vision deficiency
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.linewidth": 0.6})
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.4, 3.0), dpi=300,
                                   gridspec_kw={"width_ratios": [1, 1.25]})

    a, b = j[j.season], j[~j.season]
    ax1.scatter(a.soil_moisture, a.ndmi_mean, s=16, marker="o", color=BLUE, edgecolor="white",
                linewidth=0.5, label=f"April\u2013September (n={len(a)}, r={o['season']['r']:+.2f})")
    ax1.scatter(b.soil_moisture, b.ndmi_mean, s=18, marker="^", color=ORANGE, edgecolor="white",
                linewidth=0.5, label=f"October\u2013March (n={len(b)}, r={o['offseason']['r']:+.2f})")
    ax1.set_xlabel("Station soil moisture (%)")
    ax1.set_ylabel("Field-mean NDMI")
    ax1.set_title(f"(a) Same-day comparison, all dates: n={o['all']['n']}, r={o['all']['r']:+.2f}",
                  loc="left", fontsize=8, color=INK)
    ax1.legend(frameon=False, fontsize=7, loc="upper left", handletextpad=0.3, borderaxespad=0.2)
    ax1.set_ylim(top=ax1.get_ylim()[1] + 0.22)

    x = pd.to_datetime(series.date)
    ax2.fill_between(x, series.p05, series.p95, color=BLUE, alpha=0.22, linewidth=0)
    ax2.plot(x, series.ndmi_mean, color=BLUE, linewidth=1.2)
    ax2.set_ylabel("NDMI inside the field")
    ax2.set_title("(b) Field mean (line) and 5th\u201395th percentile of pixels (band)",
                  loc="left", fontsize=8, color=INK)
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    for ax in (ax1, ax2):
        ax.grid(True, color=GRID, linewidth=0.5)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    fig.tight_layout(w_pad=2.0)
    fig.savefig(path, dpi=300, facecolor="white", metadata={"Software": None})
    print(f"figure written: {path}")


if __name__ == "__main__":
    o, series, j = compute()
    report(o)
    # kept beside the scripts so the audit can check the text against it
    res = pathlib.Path(__file__).with_name("ndmi_station_results.json")
    res.write_text(json.dumps({k: (str(v) if isinstance(v, dt.date) else v) for k, v in o.items()},
                              indent=2), encoding="utf-8")
    print(f"results written: {res.name}")
    figure(o, series, j, pd_.PAPER / "Pic" / "NDMI_station.png")
