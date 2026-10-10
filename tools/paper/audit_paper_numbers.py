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
DB = REPO / "DB_01.db"

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
con = sqlite3.connect(DB)
rows = list(con.execute(
    "select humidity,N,P,K from NPKv1 where date(timestamp,'unixepoch') between "
    "'2026-09-01' and '2026-09-07' and N>0 and P is not null and K is not null "
    "and humidity between 15 and 60"))
N = [r[1] for r in rows]; P = [r[2] for r in rows]; K = [r[3] for r in rows]
want("in-soil readings", len(rows), f"{len(rows):,}".replace(",", chr(92) + ","),
     f"{len(rows):,}".replace(",", "{,}"))
for (xn, x), (yn, y) in ((("N", N), ("P", P)), (("N", N), ("K", K)), (("P", P), ("K", K))):
    a, b, mx, sd = linfit(x, y)
    want(f"{yn}={xn} slope", a, f"{a:.4f}")
    want(f"{yn}={xn} intercept", b, f"{abs(b):.3f}")
    want(f"{yn}={xn} max residual", mx, f"{mx:.2f}")
    want(f"{yn}={xn} residual SD", sd, f"{sd:.2f}")
    want(f"r({xn},{yn})", pearson(x, y), f"{pearson(x,y):.5f}")
want("P range low", min(P), f"{min(P):.0f}")
want("P range high", max(P), f"{max(P):.0f}")
want("K range low", min(K), f"{min(K):.0f}")
want("K range high", max(K), f"{max(K):.0f}")

# clamp
aP, bP, _, _ = linfit(N, P)
z = [r[0] for r in con.execute(
    "select P from NPKv1 where N=0 and P is not null and humidity between 15 and 60 "
    "and date(timestamp,'unixepoch') between '2026-09-01' and '2026-09-07'")]
want("clamped readings", len(z), f"{len(z):,}".replace(",", chr(92) + ","),
     f"{len(z):,}".replace(",", "{,}"))
want("clamp floor P", bP, f"{bP:.1f}")

# moisture relation and settling, from the two-soil campaign
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import insertion_analysis as ins

w = ins.within_soil()
for kod in ("59882", "59888"):
    s = w[kod]
    want(f"{kod} moisture low", s["m_lo"], f"{s['m_lo']:.1f}")
    want(f"{kod} moisture high", s["m_hi"], f"{s['m_hi']:.1f}")
    want(f"{kod} within-soil r", s["r"], f"{s['r']:.2f}")
want("59882 N low", w["59882"]["n_lo"], f"{w['59882']['n_lo']:.0f} to")
want("59882 N high", w["59882"]["n_hi"], f"{w['59882']['n_hi']:.0f}~mg/kg")
want("59882 within-soil r2", w["59882"]["r2"], f"{w['59882']['r2']:.2f}")
want("59882 within-soil slope", w["59882"]["slope"], f"{w['59882']['slope']:.2f}")
want("pooled within-soil r", w["pooled"]["r"], f"{w['pooled']['r']:.2f}")
want("pooled within-soil slope", w["pooled"]["slope"], f"{w['pooled']['slope']:.2f}")
want("moisture share of the N gap, mg/kg", w["gap"]["explained"], f"{w['gap']['explained']:.1f}")
want("moisture share of the N gap, %", w["gap"]["share"] * 100, f"{w['gap']['share']*100:.0f}~")

sv = ins.settling()
want("in-soil periods of ten minutes", sv["long"], f"the {sv['long']} periods")
want("in-soil periods of thirty minutes", sv["long30"], f"the {sv['long30']} periods")
want("moisture at 1 min, median", sv["moisture_1"]["median"], f"{sv['moisture_1']['median']:.1f}")
want("moisture at 1 min, largest", sv["moisture_1"]["max"], f"{sv['moisture_1']['max']:.1f}")
want("undisturbed moisture SD", sv["rest_sd_moisture"], f"{sv['rest_sd_moisture']:.1f}")
for m in (1, 2, 5):
    d = sv[f"nitrogen_{m}"]
    want(f"nitrogen at {m} min, median", d["median"], f"{d['median']:.1f}~mg/kg")
    want(f"nitrogen at {m} min, largest", d["max"], f"at most {d['max']:.0f})")
want("nitrogen drift 2 to 30 min, largest", sv["drift_n"]["max"], f"{sv['drift_n']['max']:.0f}~mg/kg")

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
    want("waiting at one per 5 ha", pts5 * 2, f"{pts5*2:.0f} minutes")
    want("points at one per ha", round(o["field_ha"]), f"{round(o['field_ha'])}" + chr(10) + "points",
         f"{round(o['field_ha'])} points")
    want("waiting at one per pixel", o["field_pixels"] * 2 / 60, f"{o['field_pixels']*2/60:.0f} hours")
else:
    print("note: ndmi_station_results.json not found - run ndmi_station_analysis.py (tf210 environment)")

# The forecasting model and its results are reported in a separate paper (WREN) and
# are deliberately absent from this manuscript, so nothing of them is audited here.

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
    want(f"{soil} n", len(v), f"${len(v)}$")
    for i, ch in enumerate("NPK"):
        col = [x[i] for x in v]
        want(f"{soil} {ch} mean", st.mean(col), f"{st.mean(col):.2f}")
        want(f"{soil} {ch} sd", st.stdev(col), f"{st.stdev(col):.2f}")
    mo = [x[3] for x in v]
    want(f"{soil} moisture", st.mean(mo), f"{st.mean(mo):.1f}")
    want(f"{soil} moisture sd", st.stdev(mo), f"{st.stdev(mo):.1f}")
    for key, name in (("N", "NO2/NO3-N"), ("P", "P2O5"), ("K", "K2O")):
        want(f"{soil} lab {name}", lab[kod][key], f"{lab[kod][key]:.1f}", f"{lab[kod][key]:.0f}")

# coefficients
for i, (ch, key, nm) in enumerate((("N", "N", "nitrogen"), ("P", "P", "phosphorus"),
                                   ("K", "K", "potassium"))):
    rg = st.mean([x[i] for x in soils["good"]])
    rb = st.mean([x[i] for x in soils["bad"]])
    lg, lb = lab["59882"][key], lab["59888"][key]
    a = (lb - lg) / (rb - rg); b = lg - a * rg
    want(f"{nm} A", a, f"{abs(a):.4f}")
    want(f"{nm} B", b, f"{abs(b):.2f}")

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
