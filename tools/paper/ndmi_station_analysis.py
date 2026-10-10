"""Satellite NDMI against the one ground record, Csolnok field.

Reads the NDMI GeoTIFFs, the field polygon and the station record directly
(independently of the WREN package) and reports what a single ground point can
and cannot say about the field-scale image series. Writes the figure used in
the manuscript.

Needs rasterio and geopandas, which the base Anaconda environment lacks:

    C:/Users/User/anaconda3/envs/tf210/python.exe tools/paper/ndmi_station_analysis.py

Data locations can be overridden with NDMI_DIR, FIELD_SHP, WEATHER_CSV, PAPER_DIR.
"""
import os, re, json, pathlib, math, statistics as st, datetime as dt
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.mask import mask as rio_mask
from scipy import stats
from shapely.geometry import Point

BASE = pathlib.Path(r"C:/Users/User/Documents/Projects")
NDMI_DIR = pathlib.Path(os.environ.get("NDMI_DIR", BASE / "LandCoverNDMI/NDMI_CSOLNOK"))
SHAPE = pathlib.Path(os.environ.get("FIELD_SHP", BASE / "LandCoverNDMI/ThematicMaps/Hatar_73_tomb.shp"))
WEATHER = pathlib.Path(os.environ.get("WEATHER_CSV", BASE / "SoilSensor/pivoted_all_data.csv"))
PAPER = pathlib.Path(os.environ.get("PAPER_DIR", r"C:/Users/User/Documents/GitHub/Agriculture-4351955"))
STATION = "Csolnok"
CRS = "EPSG:23700"          # Hungarian EOV; the shapefile carries no .prj


def compute():
    """Return every figure quoted in the manuscript, plus the series for the plot."""
    out = {}
    g = gpd.read_file(SHAPE)
    if g.crs is None:
        g = g.set_crs(CRS)
    poly = g.geometry.union_all() if hasattr(g.geometry, "union_all") else g.geometry.unary_union
    out["field_ha"] = poly.area / 1e4

    rows, level, sat, pix = [], {"MSIL1C": 0, "MSIL2A": 0}, {"S2A": 0, "S2B": 0}, None
    for f in sorted(NDMI_DIR.glob("*.tif")):
        m = re.match(r"(S2[AB])_(MSIL\w\w)_(\d{8})T", f.name)
        if not m:
            continue
        sat[m.group(1)] += 1
        level[m.group(2)] += 1
        d = dt.datetime.strptime(m.group(3), "%Y%m%d").date()
        with rasterio.open(f) as src:
            if pix is None:
                pix = (abs(src.transform.a), abs(src.transform.e))
            a, _ = rio_mask(src, [poly], crop=True, all_touched=False, nodata=np.nan, filled=True)
        a = a[0].astype("float64")
        a[(a < -1) | (a > 1)] = np.nan
        rows.append((d, a))

    out["scenes"] = len(rows)
    out["s2a"], out["s2b"] = sat["S2A"], sat["S2B"]
    out["l1c"], out["l2a"] = level["MSIL1C"], level["MSIL2A"]
    out["pixel_m"] = pix[0]
    out["pixel_m2"] = pix[0] * pix[1]
    by_date = {}
    for d, a in rows:
        by_date.setdefault(d, a)
    dates = sorted(by_date)
    out["first"], out["last"] = dates[0], dates[-1]
    out["gap_median_days"] = st.median([(b - a).days for a, b in zip(dates, dates[1:])])
    out["field_pixels"] = int(st.median([int(np.isfinite(a).sum()) for a in by_date.values()]))

    series = pd.DataFrame({
        "date": dates,
        "ndmi_mean": [np.nanmean(by_date[d]) for d in dates],
        "ndmi_sd": [np.nanstd(by_date[d]) for d in dates],
        "p05": [np.nanpercentile(by_date[d], 5) for d in dates],
        "p95": [np.nanpercentile(by_date[d], 95) for d in dates],
    })
    out["within_sd_median"] = float(series.ndmi_sd.median())
    out["within_sd_q1"] = float(series.ndmi_sd.quantile(.25))
    out["within_sd_q3"] = float(series.ndmi_sd.quantile(.75))
    out["within_spread_median"] = float((series.p95 - series.p05).median())
    out["temporal_sd"] = float(series.ndmi_mean.std(ddof=0))

    w = pd.read_csv(WEATHER)
    out["stations"] = int(w.station_name.nunique())
    s = w[w.station_name == STATION].copy()
    # EOV convention: X is the northing and Y the easting
    pt = Point(float(s.station_eovy.iloc[0]), float(s.station_eovx.iloc[0]))
    out["station_to_boundary_m"] = poly.distance(pt)
    out["station_to_centroid_m"] = poly.centroid.distance(pt)
    out["station_inside"] = bool(poly.contains(pt))
    s["date"] = pd.to_datetime(dict(year=s.year, month=s.month, day=s.day)).dt.date
    daily = s.groupby("date")[["soil_moisture"]].mean()
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
    print(f"  {o['stations']} stations in the network file ; {STATION} is "
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
    BLUE, ORANGE = "#2a78d6", "#eb6834"          # validated pair, categorical slots 1 and 2
    plt.rcParams.update({"font.size": 8, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.linewidth": 0.6})
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
    fig.savefig(path, dpi=300, facecolor="white")
    print(f"figure written: {path}")


if __name__ == "__main__":
    o, series, j = compute()
    report(o)
    # kept beside the scripts so the audit can check the text without rasterio
    res = pathlib.Path(__file__).with_name("ndmi_station_results.json")
    res.write_text(json.dumps({k: (str(v) if isinstance(v, dt.date) else v) for k, v in o.items()},
                              indent=2), encoding="utf-8")
    print(f"results written: {res.name}")
    figure(o, series, j, PAPER / "Pic" / "NDMI_station.png")
