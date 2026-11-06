"""Relation between the moisture and the nutrient outputs over the two-soil test.

    C:/Users/User/anaconda3/python.exe tests/2026-10_two_soil_calibration/moisture_fit.py

Each nutrient output is fitted against the moisture average (ten readings), first
alone and then together with the time since insertion, since moisture and time
change together during the test. The first ten minutes after insertion are left
out, as the readings are still settling. Writes moisture_fit_results.json.
"""
import json
import pathlib

import numpy as np
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
TESTS = {"weak": "2026-10-25_weak_soil", "good": "2026-10-27_good_soil"}
SETTLE_S = 600

out = {}
for soil, folder in TESTS.items():
    d = pd.read_csv(HERE.parent / folder / "readings.csv")
    d = d[(d.humidity >= 15) & (d.humidity <= 60) & (d.N > 0)].copy()
    d["m"] = d.humidity.rolling(10).mean()
    d["h"] = (d.timestamp - d.timestamp.iloc[0]) / 3600
    d = d[d.h * 3600 >= SETTLE_S].dropna()
    res = {"n": int(len(d)), "moisture": [round(float(d.m.min()), 1), round(float(d.m.max()), 1)]}
    for c in "NPK":
        y = d[c].to_numpy()
        a, b = np.polyfit(d.m, y, 1)
        sd_lin = float(np.std(y - np.polyval([a, b], d.m)))
        sd_quad = float(np.std(y - np.polyval(np.polyfit(d.m, y, 2), d.m)))
        X = np.c_[d.m, d.h, np.ones(len(d))]
        (am, ah, _), *_ = np.linalg.lstsq(X, y, rcond=None)
        res[c] = {"slope": float(a), "r": float(np.corrcoef(d.m, y)[0, 1]),
                  "sd_linear": sd_lin, "sd_quadratic": sd_quad,
                  "slope_with_time": float(am), "per_hour": float(ah)}
    out[soil] = res

(HERE / "moisture_fit_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
for soil, r in out.items():
    print(soil, r["n"], "readings, moisture", r["moisture"])
    for c in "NPK":
        f = r[c]
        print(f"  {c}: {f['slope']:+.2f}/%RH r={f['r']:+.2f}  with time {f['slope_with_time']:+.2f}/%RH "
              f"{f['per_hour']:+.2f}/h  SD lin {f['sd_linear']:.1f} quad {f['sd_quadratic']:.1f}")
