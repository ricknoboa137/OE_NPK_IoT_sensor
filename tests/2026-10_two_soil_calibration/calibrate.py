"""Two-soil calibration from the tests of 25-28 October 2026.

The probe stayed in the weak soil (25-27 October) and then in the good soil
(27-28 October), each kept at about 40 % moisture. With the laboratory values of
the two soils, the correction x' = A x + B is solved for each nutrient channel:

    A = (y_good - y_weak) / (x_good - x_weak),   B = y_weak - A x_weak

y is the laboratory value (nitrate-nitrogen, P2O5, K2O) and x the sensor reading.
Because the readings drift while the probe stays in a soil, x is taken in three
ways, and the coefficients are reported for each:

  matched moisture   readings whose 10-reading moving-average moisture is 40-42 %RH
  matched time       readings from 2 to 20 h after insertion (the good-soil test
                     lasted 20.4 h)
  end of test        the last hour of each test

Samples: the weak soil is laboratory sample 59888 and the good soil sample
59882, the designations used in the two-soil campaign of September 2026.

    C:/Users/User/anaconda3/python.exe tests/2026-10_two_soil_calibration/calibrate.py
"""
import csv, json, sys, pathlib, statistics as st
import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
TESTS = HERE.parent
sys.path.insert(0, str(TESTS.parent / "tools" / "paper"))
import paper_data  # location of the laboratory database (paper repository)

SOILS = {"weak": ("2026-10-25_weak_soil", "59888"), "good": ("2026-10-27_good_soil", "59882")}
LAB_KEYS = {"N": "NO2_NO3_N", "P": "P2O5", "K": "K2O"}
WINDOW = 10
MOIST_BAND = (40.0, 42.0)
TIME_BAND_H = (2.0, 20.0)


def moving_average(x, n):
    c = np.cumsum(np.insert(x, 0, 0.0))
    out = np.empty_like(x)
    out[n - 1:] = (c[n:] - c[:-n]) / n
    out[:n - 1] = c[1:n] / np.arange(1, n)
    return out


def load(folder):
    with open(TESTS / folder / "readings.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    d = {k: np.array([float(r[k]) for r in rows]) for k in rows[0]}
    d["hours"] = (d["timestamp"] - d["timestamp"][0]) / 3600
    d["moist_avg"] = moving_average(d["humidity"], WINDOW)
    return d


def lab_values():
    out = {}
    with open(paper_data.LAB_CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            code = (r.get("Mintakod") or "").strip()
            if code in ("59882", "59888"):
                out[code] = {ch: float(r[k].replace(",", ".")) for ch, k in LAB_KEYS.items()}
    return out


def windows(d):
    after_first_hour = d["hours"] >= 1
    return {
        "matched moisture": after_first_hour & (d["moist_avg"] >= MOIST_BAND[0]) & (d["moist_avg"] <= MOIST_BAND[1]),
        "matched time": (d["hours"] >= TIME_BAND_H[0]) & (d["hours"] <= TIME_BAND_H[1]),
        "end of test": d["hours"] >= d["hours"][-1] - 1,
    }


def main():
    data = {s: load(folder) for s, (folder, _) in SOILS.items()}
    lab = lab_values()
    result = {"samples": "weak soil = sample 59888, good soil = sample 59882",
              "laboratory": {s: lab[code] for s, (_, code) in SOILS.items()}, "methods": {}}
    print("laboratory (mg/kg):", json.dumps(result["laboratory"]))
    for method in ("matched moisture", "matched time", "end of test"):
        sensor = {}
        for s, d in data.items():
            m = windows(d)[method]
            sensor[s] = {"n": int(m.sum()),
                         "moisture": float(np.median(d["moist_avg"][m])),
                         "temperature": float(np.median(d["temperature"][m])),
                         **{ch: float(np.median(d[ch][m])) for ch in "NPK"}}
        coef = {}
        for ch in "NPK":
            xw, xg = sensor["weak"][ch], sensor["good"][ch]
            yw, yg = result["laboratory"]["weak"][ch], result["laboratory"]["good"][ch]
            a = (yg - yw) / (xg - xw) if xg != xw else float("nan")
            coef[ch] = {"A": a, "B": yw - a * xw,
                        "direction": "same as laboratory" if a > 0 else "opposite to laboratory"}
        result["methods"][method] = {"sensor": sensor, "coefficients": coef}
        print(f"\n{method.upper()}")
        for s in ("weak", "good"):
            v = sensor[s]
            print(f"  {s:4}  n={v['n']:6d}  moisture {v['moisture']:5.1f} %RH  temp {v['temperature']:4.1f} C   "
                  f"N {v['N']:5.1f}  P {v['P']:6.1f}  K {v['K']:6.1f}")
        for ch in "NPK":
            c = coef[ch]
            print(f"  {ch}:  A = {c['A']:+8.4f}   B = {c['B']:+9.2f}   ({c['direction']})")
    (HERE / "calibration_results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    figure(data)


def figure(data):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
    COLOR = {"weak": "#eb6834", "good": "#2a78d6"}      # validated categorical pair
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": MUTED,
                         "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                         "axes.linewidth": 0.6})
    fig, axes = plt.subplots(2, 2, figsize=(7.4, 4.8), dpi=200, sharex=True)
    panels = (("moist_avg", f"Moisture, {WINDOW}-reading average (%RH)"), ("N", "Nitrogen output (mg/kg)"),
              ("P", "Phosphorus output (mg/kg)"), ("K", "Potassium output (mg/kg)"))
    for ax, (key, title) in zip(axes.ravel(), panels):
        for s, d in data.items():
            ax.plot(d["hours"], d[key], color=COLOR[s], linewidth=0.9,
                    label=f"{s} soil (sample {SOILS[s][1]})")
        if key == "moist_avg":
            ax.axhspan(*MOIST_BAND, color=MUTED, alpha=0.12, linewidth=0)
            ax.legend(frameon=False, fontsize=7, loc="lower right")
        ax.set_title(title, loc="left", fontsize=8, color=INK)
        ax.grid(True, color=GRID, linewidth=0.5)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("Hours since insertion", color=MUTED)
    fig.suptitle("Weak and good soil, aligned at insertion (gray band: 40-42 %RH)",
                 x=0.01, ha="left", fontsize=8.5, color=INK)
    fig.tight_layout(h_pad=1.0, w_pad=2.0)
    out = HERE / "two_soil_comparison.png"
    fig.savefig(out, facecolor="white", metadata={"Software": None})
    print(f"\nfigure written: {out}")


if __name__ == "__main__":
    main()
