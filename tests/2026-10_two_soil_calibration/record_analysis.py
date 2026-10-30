"""What the October record shows about the nutrient channels, for the manuscript:
the relations between the outputs, the moisture steps within each soil, the change
of the readings between those steps, and the settling after each insertion.

    C:/Users/User/anaconda3/python.exe tests/2026-10_two_soil_calibration/record_analysis.py

Writes record_results.json beside this script; the audit reads it.
"""
import json, pathlib, statistics as st
import numpy as np
from calibrate import load, SOILS, windows, HERE


def fit(x, y):
    a, b = np.polyfit(x, y, 1)
    res = y - (a * x + b)
    return dict(a=float(a), b=float(b), r=float(np.corrcoef(x, y)[0, 1]),
                max_res=float(np.abs(res).max()), sd=float(res.std()))


def steps(d, jump=1.8, wait=0.25, span=0.5):
    """Moisture steps: the half-hour median of the moisture average rises by >= jump %RH."""
    h, m = d["hours"], d["moist_avg"]
    found, t = [], 1.0
    while t < h[-1] - (wait + span):
        before = (h >= t - span) & (h < t)
        after = (h >= t + wait) & (h < t + wait + span)
        if before.sum() > 50 and after.sum() > 50 and np.median(m[after]) - np.median(m[before]) >= jump:
            # centre on the largest rise in the neighbourhood
            cand = [t + k * 0.05 for k in range(0, 21)]
            def rise(c):
                b_ = (h >= c - span) & (h < c)
                a_ = (h >= c + wait) & (h < c + wait + span)
                return np.median(m[a_]) - np.median(m[b_])
            c = max(cand, key=rise)
            b_ = (h >= c - span) & (h < c)
            a_ = (h >= c + wait) & (h < c + wait + span)
            e = dict(hour=float(c), dM=float(np.median(m[a_]) - np.median(m[b_])))
            for ch in "NPK":
                e["d" + ch] = float(np.median(d[ch][a_]) - np.median(d[ch][b_]))
            found.append(e)
            t = c + 2.0
        else:
            t += 0.05
    return found


def between_steps(d, evs, skip=1.0):
    """Change per hour of N and of the moisture average in the stretches between steps."""
    edges = [1.0] + [e["hour"] + skip for e in evs]
    ends = [e["hour"] for e in evs] + [float(d["hours"][-1])]
    out = []
    for a, b in zip(edges, ends):
        m = (d["hours"] >= a) & (d["hours"] < b)
        if b - a < 2 or m.sum() < 100:
            continue
        out.append(dict(from_h=a, to_h=b,
                        N_per_h=float(np.polyfit(d["hours"][m], d["N"][m], 1)[0]),
                        P_per_h=float(np.polyfit(d["hours"][m], d["P"][m], 1)[0]),
                        M_per_h=float(np.polyfit(d["hours"][m], d["moist_avg"][m], 1)[0])))
    return out


def settling(d):
    """Departure from the ten-minute value after insertion."""
    def at(key, minute, half=15):
        t = minute * 60
        m = np.abs((d["hours"] * 3600) - t) <= half
        return float(np.median(d[key][m]))
    out = {}
    for key in ("N", "moist_avg"):
        ref = at(key, 10)
        out[key] = {str(mn): at(key, mn) - ref for mn in (0.5, 1, 2, 5)}
        out[key + "_10min"] = ref
        out[key + "_1h"] = at(key, 60)
    return out


data = {s: load(folder) for s, (folder, _) in SOILS.items()}
result = {}

in_soil = {s: (d["humidity"] >= 15) & (d["humidity"] <= 60) & (d["N"] > 0) for s, d in data.items()}
N = np.concatenate([d["N"][in_soil[s]] for s, d in data.items()])
P = np.concatenate([d["P"][in_soil[s]] for s, d in data.items()])
K = np.concatenate([d["K"][in_soil[s]] for s, d in data.items()])
result["n_in_soil"] = int(N.size)
result["P_N"], result["K_N"], result["K_P"] = fit(N, P), fit(N, K), fit(P, K)
result["ranges"] = dict(P=[float(P.min()), float(P.max())], K=[float(K.min()), float(K.max())],
                        N=[float(N.min()), float(N.max())])

for s, d in data.items():
    ev = steps(d)
    w = windows(d)["matched moisture"]
    result[s] = dict(
        readings=int(d["N"].size), hours=float(d["hours"][-1]),
        steps=ev, between=between_steps(d, ev), settling=settling(d),
        peak=dict(N=float(d["N"].max()), P=float(d["P"].max()), K=float(d["K"].max())),
        last_hour={ch: float(np.median(d[ch][d["hours"] >= d["hours"][-1] - 1])) for ch in "NPK"},
        last_two_hours={ch: [float(d[ch][d["hours"] >= d["hours"][-1] - 2].min()), float(d[ch][d["hours"] >= d["hours"][-1] - 2].max())] for ch in "NPK"},
        band_hours=[float(d["hours"][w].min()), float(d["hours"][w].max())],
        band_quartiles={ch: [float(np.percentile(d[ch][w], 25)), float(np.percentile(d[ch][w], 75))] for ch in "NPK"},
        temperature=[float(d["temperature"].min()), float(d["temperature"].max())],
        pH=[float(d["PH"][d["hours"] >= 1].min()), float(d["PH"][d["hours"] >= 1].max())])
    dM = [e["dM"] for e in ev]
    dN = [e["dN"] for e in ev]
    result[s]["N_per_RH_at_steps"] = (sum(dN) / sum(dM)) if ev else None

allM = [e["dM"] for s in data for e in result[s]["steps"]]
allN = [e["dN"] for s in data for e in result[s]["steps"]]
result["N_per_RH_all_steps"] = sum(allN) / sum(allM)
result["n_steps"] = len(allM)
(HERE / "record_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result, indent=1))
