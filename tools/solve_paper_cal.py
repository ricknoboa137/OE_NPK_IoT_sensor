"""Solve the microcontroller-side A and B from the two-soil calibration test.

Sensor readings: Agriculture-4351955/SoilSamplesCalibrationTest.xlsx
Laboratory values: SZ-24_ADATBAZIS.csv, matched on the Mintakod sample code.

The firmware applies  value = A * raw + B  per channel, so A and B are fitted
against the laboratory values directly. Sensor P and K are compared with the
laboratory P2O5 and K2O, following the convention already used in the
manuscript's Tables 4 and 5.
"""
import csv, statistics as st, pathlib
import openpyxl

XLSX = pathlib.Path(r"C:/Users/User/Documents/GitHub/Agriculture-4351955"
                    r"/SoilSamplesCalibrationTest.xlsx")
LAB = pathlib.Path(r"C:/Users/User/Documents/GitHub/Agriculture-4351955"
                   r"/SZ-24/SZ-24/SZ-24_ADATBAZIS.csv")

# --- sensor readings --------------------------------------------------------
wb = openpyxl.load_workbook(XLSX, data_only=True)
ws = wb[wb.sheetnames[0]]
CORRECT_TYPO = True

readings = {}
rejected = []
corrected = []
for row in list(ws.iter_rows(values_only=True))[1:]:
    if not row or row[0] is None:
        continue
    soil = str(row[0]).strip().lower()
    kod = str(row[1]).strip()
    try:
        n, p, k, moist = float(row[2]), float(row[3]), float(row[4]), float(row[5])
    except (TypeError, ValueError):
        continue
    # One row reads K = 9189 beside P = 196. The device's internal relation
    # K = 1.0079*P - 8.07 predicts 189.5, so this is a leading-digit slip for
    # 189. It is corrected rather than discarded so that all forty readings
    # are used; set CORRECT_TYPO = False to drop the row instead. The
    # conclusions are unchanged either way, only the third decimal of A moves.
    if not (0 <= k <= 3000):
        fixed = float(str(int(k))[1:]) if len(str(int(k))) > 1 else 0.0
        if CORRECT_TYPO and abs(fixed - (1.0079 * p - 8.07)) < 5.0:
            corrected.append((soil, kod, k, fixed, 1.0079 * p - 8.07))
            k = fixed
        else:
            rejected.append((soil, kod, n, p, k, moist))
            continue
    if not (0 <= n <= 3000 and 0 <= p <= 3000):
        rejected.append((soil, kod, n, p, k, moist))
        continue
    readings.setdefault((soil, kod), []).append((n, p, k, moist))

# --- laboratory values ------------------------------------------------------
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
        lab[code] = {"N": num("NO2_NO3_N"), "P": num("P2O5"), "K": num("K2O"),
                     "pH": num("pH_KCl")}

print("=" * 78)
print("SENSOR READINGS")
print("=" * 78)
for soil, kod, was, now, pred in corrected:
    print(f"  {soil} {kod}: K = {was:.0f} corrected to {now:.0f} "
          f"(internal relation predicts {pred:.1f})")
if rejected:
    for r in rejected:
        print(f"  excluded as out of range: {r}")
if corrected or rejected:
    print()
stats = {}
for (soil, kod), vals in readings.items():
    n = [v[0] for v in vals]; p = [v[1] for v in vals]
    k = [v[2] for v in vals]; mo = [v[3] for v in vals]
    stats[soil] = dict(kod=kod, n=len(vals),
                       N=st.mean(n), P=st.mean(p), K=st.mean(k), M=st.mean(mo),
                       Nsd=st.stdev(n), Psd=st.stdev(p), Ksd=st.stdev(k),
                       Msd=st.stdev(mo), Mmin=min(mo), Mmax=max(mo))
    s = stats[soil]
    print(f"  {soil.upper():5} (sample {kod})  n = {s['n']} insertions")
    print(f"        N {s['N']:7.2f} +/- {s['Nsd']:5.2f}      "
          f"P {s['P']:7.2f} +/- {s['Psd']:5.2f}      K {s['K']:7.2f} +/- {s['Ksd']:5.2f}")
    print(f"        moisture {s['M']:.1f} +/- {s['Msd']:.1f} %RH "
          f"(range {s['Mmin']:.1f}-{s['Mmax']:.1f})")

print()
print("=" * 78)
print("LABORATORY VALUES")
print("=" * 78)
for soil in ("good", "bad"):
    kod = stats[soil]["kod"]
    L = lab[kod]
    print(f"  {soil.upper():5} (sample {kod})   "
          f"NO2/NO3-N {L['N']:6.1f}   P2O5 {L['P']:6.1f}   K2O {L['K']:6.1f}   pH {L['pH']}")

print()
print("=" * 78)
print("MOISTURE CONFOUND")
print("=" * 78)
dM = stats["bad"]["M"] - stats["good"]["M"]
SENS = 1.355          # mg/kg apparent N per %RH, from paper_analysis.py section 3
print(f"  the two sets were measured at different water contents:")
print(f"    good {stats['good']['M']:.1f} %RH, bad {stats['bad']['M']:.1f} %RH, "
      f"difference {dM:+.1f} %RH")
print(f"  at the measured sensitivity of {SENS:.2f} mg/kg per %RH, that difference alone")
print(f"  accounts for {SENS*dM:+.1f} mg/kg of apparent nitrogen,")
dN = stats["bad"]["N"] - stats["good"]["N"]
print(f"  against an observed difference between the soils of {dN:+.1f} mg/kg")
print(f"  -> {abs(SENS*dM/dN)*100:.0f}% of the sensor difference is attributable to water")

print()
print("=" * 78)
print("TWO-POINT SOLUTION  value = A * raw + B")
print("=" * 78)
print(f"  {'channel':<12}{'raw good':>10}{'raw bad':>10}{'lab good':>10}{'lab bad':>10}"
      f"{'A':>12}{'B':>12}")
print("  " + "-" * 74)
cmds, warns = [], []
for ch, key, name in (("N", "N", "nitrogen"), ("P", "P", "phosphorus"), ("K", "K", "potassium")):
    rg, rb = stats["good"][ch], stats["bad"][ch]
    lg = lab[stats["good"]["kod"]][key]
    lb = lab[stats["bad"]["kod"]][key]
    a = (lb - lg) / (rb - rg)
    b = lg - a * rg
    print(f"  {name:<12}{rg:10.2f}{rb:10.2f}{lg:10.1f}{lb:10.1f}{a:12.5f}{b:12.3f}")
    cmds.append(f"cal set {name} {a:.5f} {b:.5f}")
    if a < 0:
        warns.append(f"{name}: NEGATIVE GAIN. The sensor reported more where the laboratory "
                     f"reports less ({rg:.0f} -> {rb:.0f} against {lg:.0f} -> {lb:.0f}). "
                     f"The two soils are ranked in opposite order by the instrument and by "
                     f"the laboratory.")
    if b < 0:
        warns.append(f"{name}: B is negative, so a raw reading below {-b/a:.1f} yields a "
                     f"negative concentration.")
    if abs(a) > 100:
        warns.append(f"{name}: |A| = {abs(a):.1f} is implausibly large.")

if warns:
    print()
    print("  WARNINGS")
    for w in warns:
        print(f"    - {w}")

print()
print("  commands (only if these coefficients are judged meaningful):")
for c in cmds:
    print(f"    {c}")

print()
print("=" * 78)
print("DIRECTION CHECK")
print("=" * 78)
for ch, key, name in (("N", "N", "nitrogen"), ("P", "P", "phosphorus"), ("K", "K", "potassium")):
    sd = stats["bad"][ch] - stats["good"][ch]
    ld = lab[stats["bad"]["kod"]][key] - lab[stats["good"]["kod"]][key]
    agree = "agree" if (sd > 0) == (ld > 0) else "DISAGREE"
    print(f"  {name:<12} sensor bad-good {sd:+8.2f}    laboratory bad-good {ld:+8.1f}    {agree}")
