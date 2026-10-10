"""What the two-soil campaign shows about (a) how the nitrogen output varies with
the moisture output between placements in one and the same soil, and (b) how
long a reading takes to settle after an insertion.

Sources: the forty transcribed readings (calibration workbook) and the 5 s log
(data/sensor_log.csv.gz in the paper repository). The log is in UTC; the workbook is in local time (UTC+2 in
September 2026), so the campaign runs from 12:00 UTC on 5 September to 17:30
UTC on 7 September.

    C:/Users/User/anaconda3/python.exe tools/paper/insertion_analysis.py
"""
import sys
import os, sqlite3, pathlib, statistics as st
import openpyxl

PAPER = pathlib.Path(os.environ.get(
    "PAPER_DIR", r"C:/Users/User/Documents/GitHub/Agriculture-4351955"))
REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paper_data          # the versioned sensor log, in the paper repository
XLSX = PAPER / "SoilSamplesCalibrationTest.xlsx"

CAMPAIGN = ("2026-09-05 12:00", "2026-09-07 17:30")   # UTC
MIN_EPISODE_S = 600          # the probe stayed in soil at least ten minutes
REFERENCE_MIN = 10           # readings are compared with their value at ten minutes


def pearson(a, b):
    ma, mb = st.mean(a), st.mean(b)
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((y - mb) ** 2 for y in b) ** 0.5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


def slope(x, y):
    mx, my = st.mean(x), st.mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / sum((a - mx) ** 2 for a in x)


def within_soil():
    """Nitrogen output against moisture output across the recorded insertions."""
    ws = openpyxl.load_workbook(XLSX, data_only=True).worksheets[0]
    soils = {}
    for r in list(ws.iter_rows(values_only=True))[1:]:
        if r[0] is None:
            continue
        soils.setdefault(str(r[0]).strip().lower(), []).append((float(r[5]), float(r[2])))
    out, pm, pn = {}, [], []
    for name, kod in (("good", "59882"), ("bad", "59888")):
        m = [v[0] for v in soils[name]]
        n = [v[1] for v in soils[name]]
        r = pearson(m, n)
        out[kod] = dict(n=len(m), m_lo=min(m), m_hi=max(m), n_lo=min(n), n_hi=max(n),
                        r=r, r2=r * r, slope=slope(m, n), m_mean=st.mean(m), n_mean=st.mean(n))
        pm += [x - st.mean(m) for x in m]
        pn += [y - st.mean(n) for y in n]
    r = pearson(pm, pn)
    out["pooled"] = dict(n=len(pm), r=r, r2=r * r, slope=slope(pm, pn))
    gap_m = out["59888"]["m_mean"] - out["59882"]["m_mean"]
    gap_n = out["59888"]["n_mean"] - out["59882"]["n_mean"]
    out["gap"] = dict(moisture=gap_m, nitrogen=gap_n,
                      explained=out["pooled"]["slope"] * gap_m,
                      share=out["pooled"]["slope"] * gap_m / gap_n)
    return out


def _episodes():
    con = paper_data.log_connection()
    rows = con.execute(
        "select timestamp, humidity, N from NPKv1 where timestamp between strftime('%s',?) "
        "and strftime('%s',?) and humidity is not null and N is not null order by timestamp",
        CAMPAIGN).fetchall()
    eps, cur = [], []
    for t, h, n in rows:
        if 15 <= h <= 60 and n > 0:                 # electrodes in soil
            if cur and t - cur[-1][0] > 20:
                eps.append(cur); cur = []
            cur.append((t, h, n))
        elif cur:
            eps.append(cur); cur = []
    if cur:
        eps.append(cur)
    return eps


def _at(e, minutes, col, window=30):
    """Median of a column in a window centred on `minutes` after insertion."""
    t0 = e[0][0] + minutes * 60
    v = [x[col] for x in e if abs(x[0] - t0) <= window / 2]
    return st.median(v) if v else None


def settling():
    """Departure of each output from its ten-minute value, and later drift."""
    eps = _episodes()
    long_ = [e for e in eps if e[-1][0] - e[0][0] >= MIN_EPISODE_S]
    out = dict(episodes=len(eps), long=len(long_))
    for col, name in ((1, "moisture"), (2, "nitrogen")):
        for m in (0.5, 1, 2, 5):
            d = [abs(_at(e, m, col) - _at(e, REFERENCE_MIN, col)) for e in long_
                 if _at(e, m, col) is not None and _at(e, REFERENCE_MIN, col) is not None]
            out[f"{name}_{m}"] = dict(median=st.median(d), max=max(d), n=len(d))
    l30 = [e for e in long_ if e[-1][0] - e[0][0] >= 1800]
    dn = [_at(e, 30, 2) - _at(e, 2, 2) for e in l30]
    out["long30"] = len(l30)
    out["drift_n"] = dict(median=st.median(abs(x) for x in dn), max=max(abs(x) for x in dn),
                          lo=min(dn), hi=max(dn))
    # scatter of an undisturbed probe: last five minutes of each long episode
    out["rest_sd_moisture"] = st.median(
        st.pstdev([x[1] for x in e if x[0] >= e[-1][0] - 300]) for e in long_)
    out["rest_sd_nitrogen"] = st.median(
        st.pstdev([x[2] for x in e if x[0] >= e[-1][0] - 300]) for e in long_)
    return out


if __name__ == "__main__":
    w = within_soil()
    print("NITROGEN OUTPUT AGAINST MOISTURE OUTPUT, ACROSS INSERTIONS IN ONE SOIL")
    for kod in ("59882", "59888"):
        s = w[kod]
        print(f"  sample {kod}: n={s['n']}  moisture {s['m_lo']:.1f}-{s['m_hi']:.1f} %RH  "
              f"N {s['n_lo']:.0f}-{s['n_hi']:.0f} mg/kg  r={s['r']:+.3f}  r2={s['r2']:.3f}  "
              f"slope={s['slope']:+.2f} mg/kg per %RH")
    p = w["pooled"]
    print(f"  pooled, each soil centred on its own mean: n={p['n']}  r={p['r']:+.3f}  r2={p['r2']:.3f}  "
          f"slope={p['slope']:+.2f} mg/kg per %RH")
    g = w["gap"]
    print(f"  between the soils: moisture gap {g['moisture']:.1f} %RH, nitrogen gap {g['nitrogen']:.2f} mg/kg ; "
          f"pooled slope x moisture gap = {g['explained']:.1f} mg/kg = {g['share']*100:.0f}% of the nitrogen gap")

    s = settling()
    print(f"\nSETTLING AFTER INSERTION  ({CAMPAIGN[0]} to {CAMPAIGN[1]} UTC)")
    print(f"  in-soil periods: {s['episodes']} ; lasting at least ten minutes: {s['long']}")
    for name, unit in (("moisture", "%RH"), ("nitrogen", "mg/kg")):
        for m in (0.5, 1, 2, 5):
            d = s[f"{name}_{m}"]
            print(f"  {name:9} at {m:>3} min vs 10 min: median {d['median']:.1f} {unit}, largest {d['max']:.1f}")
    print(f"  periods of at least thirty minutes: {s['long30']} ; nitrogen change from 2 to 30 min: "
          f"median {s['drift_n']['median']:.1f} mg/kg, largest {s['drift_n']['max']:.1f} "
          f"(range {s['drift_n']['lo']:+.1f} to {s['drift_n']['hi']:+.1f})")
    print(f"  undisturbed probe over five minutes: moisture SD {s['rest_sd_moisture']:.2f} %RH, "
          f"nitrogen SD {s['rest_sd_nitrogen']:.2f} mg/kg")
