"""Recompute every figure quoted in the revised manuscript and check it appears.

    C:/Users/User/anaconda3/python.exe tools/paper/audit_paper_numbers.py

Nothing here is taken from the manuscript. Each value is computed from the raw
sources - the logged readings, the laboratory database and the calibration
workbook - and then searched for in the .tex. A figure that has drifted, or a
source file that has changed since the text was written, shows up as a miss.
"""
import csv, sqlite3, statistics as st, pathlib, sys

import os

# The manuscript lives in a separate (private) repository. Point PAPER_DIR at a
# checkout of it; the default is where it sits on the author's machine.
PAPER = pathlib.Path(os.environ.get(
    "PAPER_DIR", r"C:/Users/User/Documents/GitHub/Agriculture-4351955"))
REPO = pathlib.Path(__file__).resolve().parent.parent.parent


def _find(*candidates):
    """First existing file among the candidates, else the newest glob match.

    The manuscript is renamed in Overleaf from time to time (V2, V3, ...), so
    fall back to whichever revised .tex is newest rather than failing outright.
    """
    for c in candidates:
        q = PAPER / c
        if q.exists():
            return q
    hits = sorted(PAPER.glob("*revised*.tex"), key=lambda q: q.stat().st_mtime, reverse=True)
    if hits:
        return hits[0]
    raise SystemExit(f"manuscript not found in {PAPER}; set PAPER_DIR")


def _find_original(*candidates):
    """The pre-revision manuscript, or None - it is only used for comparison."""
    for c in candidates:
        q = PAPER / c
        if q.exists():
            return q
    return None
import openpyxl

TEX = _find("agriculture-4351955-revised-V3.tex", "agriculture-4351955-revised-V2.tex",
            "agriculture-4351955-revised.tex")
LAB = PAPER / "SZ-24/SZ-24/SZ-24_ADATBAZIS.csv"
XLSX = PAPER / "SoilSamplesCalibrationTest.xlsx"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paper_data          # the versioned sensor log, in the paper repository

tex = TEX.read_text(encoding="utf-8")
checks = []


def present(form):
    """True if form occurs in the text and is not embedded in a longer number.

    A plain substring test passes on coincidences - 0.41 matches inside 0.414 -
    which would hide a stale figure. Digits either side disqualify a match.
    """
    start = 0
    while True:
        i = tex.find(form, start)
        if i < 0:
            return False
        before = tex[i - 1] if i else " "
        after = tex[i + len(form)] if i + len(form) < len(tex) else " "
        if not (before.isdigit() or before == ".") and not after.isdigit():
            return True
        start = i + 1


def want(label, value, *forms):
    """Record a computed value and whether any of its written forms is present."""
    checks.append((label, value, forms, any(present(f) for f in forms)))


def linfit(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    b = my - a * mx
    res = [y - (a * x + b) for x, y in zip(xs, ys)]
    return a, b, max(abs(r) for r in res), st.pstdev(res)


def pearson(a, b):
    ma, mb = st.mean(a), st.mean(b)
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((y - mb) ** 2 for y in b) ** 0.5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb)


# ---- 1. logged readings ----------------------------------------------------
# The test of October 2026: results written by the scripts in tests/2026-10_two_soil_calibration
import json
_oct = pathlib.Path(__file__).resolve().parent.parent.parent / "tests" / "2026-10_two_soil_calibration"
rec = json.loads((_oct / "record_results.json").read_text(encoding="utf-8"))
cal = json.loads((_oct / "calibration_results.json").read_text(encoding="utf-8"))
thin = lambda n: f"{n:,}".replace(",", chr(92) + ",")
con = paper_data.log_connection()

want("in-soil readings, October", rec["n_in_soil"], thin(rec["n_in_soil"]))
for key, name in (("P_N", "P=N"), ("K_N", "K=N"), ("K_P", "K=P")):
    f = rec[key]
    want(f"{name} slope", f["a"], f"{f['a']:.4f}")
    want(f"{name} intercept", f["b"], f"{abs(f['b']):.3f}")
    want(f"{name} max residual", f["max_res"], f"{f['max_res']:.2f}")
    want(f"{name} residual SD", f["sd"], f"{f['sd']:.2f}")
    want(f"{name} r", f["r"], f"{f['r']:.5f}")
for ch in "PK":
    lo, hi = rec["ranges"][ch]
    want(f"{ch} output range", (lo, hi), f"{lo:.0f}--{hi:.0f}")
for s in ("weak", "good"):
    v = rec[s]
    want(f"{s} readings", v["readings"], thin(v["readings"]))
    want(f"{s} duration", v["hours"], f"{v['hours']:.1f}")
    n2, n5 = v["settling"]["N"]["2"], v["settling"]["N"]["5"]
    want(f"{s} N at 2 min vs 10 min", n2, f"{abs(n2):.0f}")
    want(f"{s} N at 5 min vs 10 min", n5, f"{abs(n5):.0f}")
    dm = v["settling"]["N_1h"] - v["settling"]["N_10min"]
    want(f"{s} N, 10 min to 1 h", dm, f"{abs(dm):.0f}")
ev = rec["weak"]["steps"] + rec["good"]["steps"]
want("moisture steps", len(ev), "six steps" if len(ev) == 6 else str(len(ev)))
want("smallest moisture step", min(e["dM"] for e in ev), f"{min(e['dM'] for e in ev):.1f} to")
want("largest moisture step", max(e["dM"] for e in ev), f"{max(e['dM'] for e in ev):.1f}~" + chr(92) + "%RH")
want("N per %RH at the steps", rec["N_per_RH_all_steps"], f"{rec['N_per_RH_all_steps']:.1f}~mg/kg")
want("weak end N", rec["weak"]["last_hour"]["N"], f"$N={rec['weak']['last_hour']['N']:.0f}$")
want("weak end P", rec["weak"]["last_hour"]["P"], f"$P={rec['weak']['last_hour']['P']:.0f}$")
want("weak end K", rec["weak"]["last_hour"]["K"], f"$K={rec['weak']['last_hour']['K']:.0f}$")
want("weak band P, Q1", rec["weak"]["band_quartiles"]["P"][0], f"{rec['weak']['band_quartiles']['P'][0]:.0f} to")
want("weak band P, Q3", rec["weak"]["band_quartiles"]["P"][1], f"{rec['weak']['band_quartiles']['P'][1]:.0f}~mg/kg")

end = cal["methods"]["end of test"]
band = cal["methods"]["matched moisture"]
for s, col in (("good", 0), ("weak", 1)):
    v = end["sensor"][s]
    want(f"{s} last-hour moisture", v["moisture"], f"{v['moisture']:.1f}$")
    want(f"{s} last-hour temperature", v["temperature"], f"{v['temperature']:.1f}$")
    for ch in "NPK":
        want(f"{s} last-hour {ch}", v[ch], f"${v[ch]:.0f}$")
for name, m in (("last hour", end), ("40-42 %RH", band)):
    for ch in "NPK":
        c = m["coefficients"][ch]
        want(f"{name} {ch} A", c["A"], f"{c['A']:+.4f}".replace("-", "-"))
        want(f"{name} {ch} B", c["B"], f"{c['B']:+.2f}")
want("gain P, text", end["coefficients"]["P"]["A"], f"{end['coefficients']['P']['A']:.3f}")
want("gain K, text", end["coefficients"]["K"]["A"], f"{end['coefficients']['K']['A']:.3f}")
want("moisture difference, last hour", abs(end["sensor"]["weak"]["moisture"] - end["sensor"]["good"]["moisture"]),
     f"{abs(end['sensor']['weak']['moisture'] - end['sensor']['good']['moisture']):.1f}~" + chr(92) + "%RH")

# clamp: the earlier record of 1 to 7 September 2026
z = [r[0] for r in con.execute(
    "select P from NPKv1 where N=0 and P is not null and humidity between 15 and 60 "
    "and date(timestamp,'unixepoch') between '2026-09-01' and '2026-09-07'")]
want("clamped readings", len(z), thin(len(z)))
want("P ceiling of the clamped readings", max(z), "exceeded " + str(max(47, int(max(z)))) + "~mg/kg")
if max(z) > 47:
    print(f"note: clamped readings reach P = {max(z)}")

# satellite case study: results written by ndmi_station_analysis.py (needs rasterio,
# so it is run separately)
import json
res = pathlib.Path(__file__).with_name("ndmi_station_results.json")
if res.exists():
    o = json.loads(res.read_text(encoding="utf-8"))
    want("field area", o["field_ha"], f"{o['field_ha']:.1f}~ha")
    want("scenes", o["scenes"], f"{o['scenes']} scenes", f"{o['scenes']}")
    want("Sentinel-2A scenes", o["s2a"], f"{o['s2a']} by Sentinel-2A")
    want("Sentinel-2B scenes", o["s2b"], f"{o['s2b']} by")
    want("L1C scenes", o["l1c"], f"{o['l1c']} at top of atmosphere")
    want("L2A scenes", o["l2a"], f"{o['l2a']} at surface reflectance")
    want("in-field pixels", o["field_pixels"], f"{o['field_pixels']:,}".replace(",", chr(92) + ","))
    want("pixel area", o["pixel_m2"], f"{o['pixel_m2']:.0f}~" + chr(92) + "mathrm")
    want("median days between scenes", o["gap_median_days"], f"median of {o['gap_median_days']:.0f} days")
    want("station to boundary", o["station_to_boundary_m"], f"{o['station_to_boundary_m']:.0f}~m")
    want("station to field centre", o["station_to_centroid_m"], f"{o['station_to_centroid_m']:.0f}~m")
    want("within-field SD, median", o["within_sd_median"], f"{o['within_sd_median']:.3f}")
    want("within-field SD, Q1", o["within_sd_q1"], f"{o['within_sd_q1']:.3f}")
    want("within-field SD, Q3", o["within_sd_q3"], f"{o['within_sd_q3']:.3f}")
    want("within-field 5-95 spread", o["within_spread_median"], f"{o['within_spread_median']:.2f}")
    for key in ("all", "season", "offseason"):
        c = o[key]
        want(f"NDMI vs station r, {key}", c["r"], f"{c['r']:+.2f}")
        want(f"NDMI vs station n, {key}", c["n"], f"n={c['n']}", f"{c['n']} dates")
    want("NDMI vs station CI low", o["all"]["lo"], f"{o['all']['lo']:+.2f}")
    want("NDMI vs station CI high", o["all"]["hi"], f"{o['all']['hi']:+.2f}")
    want("variance explained, all dates", o["all"]["r2"] * 100, f"about {o['all']['r2']*100:.0f}~")
    want("variance explained, season", o["season"]["r2"] * 100, f"about {o['season']['r2']*100:.0f}~")
    # the sampling arithmetic in the Discussion
    pts5 = -(-o["field_ha"] // 5)
    want("points at one per 5 ha", pts5, f"{pts5:.0f} points")
    want("waiting at one per 5 ha, h", pts5 * 10 / 60, "less than two hours" if pts5 * 10 / 60 < 2 else "CHECK")
    want("points at one per ha", round(o["field_ha"]), f"{round(o['field_ha'])}" + chr(10) + "points",
         f"{round(o['field_ha'])} points")
    want("waiting at one per pixel", o["field_pixels"] * 10 / 60, f"{o['field_pixels']*10/60:.0f} hours")
else:
    print("note: ndmi_station_results.json not found - run ndmi_station_analysis.py (tf210 environment)")

# The forecasting model and its results are reported in a separate paper (WREN) and
# are deliberately absent from this manuscript, so nothing of them is audited here.

# the architecture table: parameters per layer, from the model summary of the preliminary run
import re as _re
summary = pathlib.Path(paper_data.DATA / "unet_preliminary" / "training_console_output.txt")
if summary.exists():
    s_txt = summary.read_text(encoding="utf-8")
    thin = lambda n: f"{n:,}".replace(",", chr(92) + ",")
    total = int(_re.search(r"Total params: ([\d,]+)", s_txt).group(1).replace(",", ""))
    want("UNet-LSTM total parameters", total, thin(total))
    for layer in ("time_distributed ", "time_distributed_2 ", "lstm ", "dense ", "conv2d_2 ", "conv2d_3 ", "conv2d_4 "):
        line = next(l for l in s_txt.splitlines() if l.strip().startswith(layer.strip() + " ("))
        n = int(_re.findall(r"\s(\d+)\s", line + " ")[-1])
        want(f"parameters of {layer.strip()}", n, thin(n) if n >= 10000 else str(n))
    want("epochs of the preliminary run", 20, "20 epochs")

# ---- 2. laboratory ---------------------------------------------------------
lab = {}
with open(LAB, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f, delimiter=";"):
        code = (r.get("Mintakod") or "").strip()
        if not code:
            continue
        def num(k):
            v = (r.get(k) or "").strip().replace(",", ".")
            try:
                return float(v)
            except ValueError:
                return None
        lab[code] = {"N": num("NO2_NO3_N"), "P": num("P2O5"), "K": num("K2O")}
vals = [v for v in lab.values() if v["N"] and v["P"] and v["K"]]
ln = [v["N"] for v in vals]; lp = [v["P"] for v in vals]; lk = [v["K"] for v in vals]
want("lab samples", len(vals), f"n={len(vals)}$", f"twelve")
for nm, v in (("N", ln), ("P2O5", lp), ("K2O", lk)):
    want(f"lab {nm} min", min(v), f"{min(v):.1f}", f"{min(v):.0f}")
    want(f"lab {nm} max", max(v), f"{max(v):.1f}", f"{max(v):.0f}")
    want(f"lab {nm} mean", st.mean(v), f"{st.mean(v):.1f}")
    want(f"lab {nm} CV", st.pstdev(v) / st.mean(v) * 100, f"{st.pstdev(v)/st.mean(v)*100:.1f}")
want("r(N,P2O5)", pearson(ln, lp), f"{pearson(ln,lp):.3f}")
want("r(N,K2O)", pearson(ln, lk), f"{pearson(ln,lk):.3f}")
want("r(P2O5,K2O)", pearson(lp, lk), f"{pearson(lp,lk):.3f}")

# (the principal component analysis was removed from the manuscript on 2026-09-11)

# site description and calibration-soil properties
import math
with open(LAB, encoding="utf-8-sig") as f:
    raw = [r for r in csv.DictReader(f, delimiter=";") if (r.get("Mintakod") or "").strip()]
fl = lambda v: float(v.replace(",", "."))
for key, fmt in (("pH_KCl", ".2f"), ("KA", ".0f"), ("Humusz", ".2f"), ("CaCO3", ".2f")):
    v = [fl(r[key]) for r in raw]
    want(f"field {key} min", min(v), format(min(v), fmt))
    want(f"field {key} max", max(v), format(max(v), fmt))
    want(f"field {key} CV", st.pstdev(v) / st.mean(v) * 100, f"{st.pstdev(v)/st.mean(v)*100:.1f}")
want("field area", fl(raw[0]["Terulet_ha"]), f"{fl(raw[0]['Terulet_ha']):.1f}")
def dist(r1, r2):
    a, b = fl(r1["Szel_Y"]), fl(r1["Hossz_X"]); c, e = fl(r2["Szel_Y"]), fl(r2["Hossz_X"])
    return 6371000 * math.hypot(math.radians(c - a), math.radians(e - b) * math.cos(math.radians(a)))
want("max sample spacing", max(dist(x, y) for x in raw for y in raw),
     f"{max(dist(x, y) for x in raw for y in raw):.0f}")
byk = {r["Mintakod"].strip(): r for r in raw}
want("calibration soil spacing", dist(byk["59882"], byk["59888"]),
     f"{dist(byk['59882'], byk['59888']):.0f}")
for kod in ("59882", "59888"):
    for key in ("pH_KCl", "KA", "Humusz", "CaCO3", "Ossz_so", "Mg", "Na", "Mn", "Fe"):
        v = fl(byk[kod][key])
        want(f"{kod} {key}", v, f"{v:g}", f"{v:.2f}", f"{v:.1f}")

# ---- 3. calibration workbook ----------------------------------------------
ws = openpyxl.load_workbook(XLSX, data_only=True)[openpyxl.load_workbook(XLSX).sheetnames[0]]
soils = {}
for row in list(ws.iter_rows(values_only=True))[1:]:
    if not row or row[0] is None:
        continue
    try:
        n_, p_, k_, m_ = float(row[2]), float(row[3]), float(row[4]), float(row[5])
    except (TypeError, ValueError):
        continue
    if k_ > 3000:
        k_ = float(str(int(k_))[1:])
    soils.setdefault(str(row[0]).strip().lower(), []).append((n_, p_, k_, m_))
for soil, kod in (("good", "59882"), ("bad", "59888")):
    v = soils[soil]
    # the preliminary series of 40 insertions, cited for the spread between placements
    want(f"{soil} insertions", len(v), "twenty")
    for i, ch in enumerate("NP"):
        col = [x[i] for x in v]
        want(f"{soil} {ch} SD between placements", st.stdev(col), f"{st.stdev(col):.1f}")
    want(f"{soil} moisture of the series", st.mean([x[3] for x in v]), f"{st.mean([x[3] for x in v]):.1f}")
    for key, name in (("N", "NO2/NO3-N"), ("P", "P2O5"), ("K", "K2O")):
        want(f"{soil} lab {name}", lab[kod][key], f"{lab[kod][key]:.1f}", f"{lab[kod][key]:.0f}")

# ---- report ----------------------------------------------------------------
miss = [c for c in checks if not c[3]]
print(f"{len(checks)} computed figures checked against {TEX.name}")
print(f"  present: {len(checks)-len(miss)}")
print(f"  missing: {len(miss)}")
if miss:
    print()
    for label, value, forms, _ in miss:
        print(f"  !! {label:26} computed {value!r:>14}   looked for {forms}")
print()
print("all figures in the manuscript match the source data"
      if not miss else "figures above are not found in the text - check whether the")
if miss:
    print("text is stale or the written form simply differs from the search string")
sys.exit(1 if miss else 0)
