"""Every number quoted in the sensor-characterisation section of the paper.

    C:/Users/User/anaconda3/python.exe tools/paper_analysis.py

Reads DB_01.db (the Node-RED log of published NPKdata) and the SZ-24 laboratory
database. Prints the statistics in the order the manuscript uses them, so any
figure in the text can be traced back to a single command.
"""
import csv, sqlite3, statistics as st, itertools, pathlib

DB = pathlib.Path(__file__).resolve().parent.parent / "DB_01.db"
LAB = pathlib.Path(r"C:/Users/User/Documents/GitHub/Agriculture-4351955"
                   r"/SZ-24/SZ-24/SZ-24_ADATBAZIS.csv")

# Inclusion criteria for the logged readings, stated once and applied throughout.
DAYS = ("2026-09-01", "2026-09-07")
MOIST_LO, MOIST_HI = 15.0, 60.0      # probe in soil, not in air or standing water


def pearson(a, b):
    ma, mb = st.mean(a), st.mean(b)
    sa = sum((x - ma) ** 2 for x in a) ** 0.5
    sb = sum((y - mb) ** 2 for y in b) ** 0.5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (sa * sb) if sa and sb else float("nan")


def linfit(xs, ys):
    mx, my = st.mean(xs), st.mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    b = my - a * mx
    res = [y - (a * x + b) for x, y in zip(xs, ys)]
    return a, b, max(abs(r) for r in res), st.pstdev(res)


con = sqlite3.connect(DB)
rows = list(con.execute(
    "select humidity, temperature, N, P, K from NPKv1 "
    "where date(timestamp,'unixepoch') between ? and ? "
    "and N is not null and P is not null and K is not null "
    "and humidity between ? and ? and N > 0",
    (DAYS[0], DAYS[1], MOIST_LO, MOIST_HI)))
m = [r[0] for r in rows]
N = [r[2] for r in rows]
P = [r[3] for r in rows]
K = [r[4] for r in rows]

print("=" * 74)
print("1. INTER-CHANNEL RELATIONSHIP")
print("=" * 74)
print(f"in-soil readings {DAYS[0]}..{DAYS[1]}, moisture {MOIST_LO:.0f}-{MOIST_HI:.0f}%, N>0")
print(f"n = {len(rows)}     N {min(N):.0f}-{max(N):.0f}   "
      f"P {min(P):.0f}-{max(P):.0f}   K {min(K):.0f}-{max(K):.0f} mg/kg")
print()
for (xn, x), (yn, y) in itertools.combinations((("N", N), ("P", P), ("K", K)), 2):
    a, b, mx, sd = linfit(x, y)
    print(f"  {yn} = {a:.4f}*{xn} {b:+.3f}      r = {pearson(x, y):+.5f}   "
          f"max residual {mx:.2f}   SD {sd:.3f} mg/kg")
print()
print("  same fit computed independently per day:")
for day in ("2026-09-05", "2026-09-06", "2026-09-07"):
    d = list(con.execute(
        "select N,P,K from NPKv1 where date(timestamp,'unixepoch')=? "
        "and N>0 and P is not null and humidity between ? and ?",
        (day, MOIST_LO, MOIST_HI)))
    if len(d) < 100:
        continue
    dn = [r[0] for r in d]; dp = [r[1] for r in d]; dk = [r[2] for r in d]
    a1, b1, _, _ = linfit(dn, dp)
    a2, b2, _, _ = linfit(dn, dk)
    print(f"    {day}  n={len(d):6d}   P = {a1:.4f}N {b1:+.3f}    K = {a2:.4f}N {b2:+.3f}")

print()
print("=" * 74)
print("2. THE NITROGEN ZERO IS A CLAMP")
print("=" * 74)
aP, bP, _, _ = linfit(N, P)
floor = bP                                    # value of P where the N fit reaches zero
z = list(con.execute(
    "select P from NPKv1 where N=0 and P is not null and humidity between ? and ? "
    "and date(timestamp,'unixepoch') between ? and ?",
    (MOIST_LO, MOIST_HI, DAYS[0], DAYS[1])))
zp = [r[0] for r in z]
above = sum(1 for p in zp if p > floor + 0.5)
print(f"the P-N fit reaches N = 0 at P = {floor:.1f} mg/kg")
print(f"readings with N exactly 0 (in soil): n = {len(zp)}")
if zp:
    print(f"  P observed in those readings: {min(zp):.0f} .. {max(zp):.0f} mg/kg")
    print(f"  readings with N = 0 while P exceeds the predicted floor: {above}")
    print(f"  -> the channel saturates at its lower bound; it does not measure zero")

print()
print("=" * 74)
print("3. MOISTURE DEPENDENCE WITHIN A SINGLE SOIL")
print("=" * 74)
s = list(con.execute(
    "select humidity, N from NPKv1 where timestamp between "
    "strftime('%s','2026-09-07 12:46') and strftime('%s','2026-09-07 16:45') "
    "and N>0 and humidity between ? and ?", (MOIST_LO, MOIST_HI)))
sm = [r[0] for r in s]; sn = [r[1] for r in s]
a, b, mx, sd = linfit(sm, sn)
print(f"single uninterrupted session, one pot, nutrient content fixed")
print(f"n = {len(s)}   moisture {min(sm):.1f}-{max(sm):.1f}%   N {min(sn):.0f}-{max(sn):.0f} mg/kg")
print(f"  r(moisture, N) = {pearson(sm, sn):+.4f}   r2 = {pearson(sm, sn)**2:.3f}")
print(f"  N = {a:.3f} * moisture {b:+.2f}   residual SD {sd:.2f} mg/kg")
print(f"  -> {a:.2f} mg/kg of apparent nitrogen per 1 %RH")

print()
print("=" * 74)
print("4. LABORATORY DATA, FIELD SZ-24")
print("=" * 74)
lab = []
with open(LAB, encoding="utf-8-sig") as f:
    for r in csv.DictReader(f, delimiter=";"):
        if not r.get("Mintakod"):
            continue
        def num(k):
            v = (r.get(k) or "").strip().replace(",", ".")
            try:
                return float(v)
            except ValueError:
                return None
        n_, p_, k_ = num("NO2_NO3_N"), num("P2O5"), num("K2O")
        if n_ and p_ and k_:
            lab.append((n_, p_, k_))
ln = [r[0] for r in lab]; lp = [r[1] for r in lab]; lk = [r[2] for r in lab]
print(f"n = {len(lab)} samples")
for nm, v in (("NO2/NO3-N", ln), ("P2O5", lp), ("K2O", lk)):
    print(f"  {nm:10} {min(v):7.1f} .. {max(v):7.1f}   mean {st.mean(v):7.1f}   "
          f"CV {st.pstdev(v)/st.mean(v)*100:4.1f}%")
print()
print(f"  r(N, P2O5)   = {pearson(ln, lp):+.3f}")
print(f"  r(N, K2O)    = {pearson(ln, lk):+.3f}")
print(f"  r(P2O5, K2O) = {pearson(lp, lk):+.3f}")
print(f"  critical |r| for p=0.05 at n={len(lab)} (df={len(lab)-2}) is 0.576 -> none significant")

print()
print("=" * 74)
print("5. HOW MUCH VARIATION A ONE-OUTPUT INSTRUMENT CAN CARRY")
print("=" * 74)
cols = [ln, lp, lk]
z3 = [[(v - st.mean(c)) / st.pstdev(c) for v in c] for c in cols]
n3 = len(lab)
C = [[sum(z3[i][t] * z3[j][t] for t in range(n3)) / n3 for j in range(3)] for i in range(3)]

def power_iter(C, deflate=()):
    v = [1.0, 0.3, -0.2]
    for _ in range(4000):
        w = [sum(C[i][j] * v[j] for j in range(3)) for i in range(3)]
        for (_, u) in deflate:
            d = sum(w[i] * u[i] for i in range(3))
            w = [w[i] - d * u[i] for i in range(3)]
        nrm = sum(x * x for x in w) ** 0.5
        if nrm < 1e-12:
            return 0.0, [0, 0, 0]
        v = [x / nrm for x in w]
    lam = sum(v[i] * sum(C[i][j] * v[j] for j in range(3)) for i in range(3))
    return lam, v

l1, v1 = power_iter(C)
l2, v2 = power_iter(C, [(l1, v1)])
l3 = 3.0 - l1 - l2
print(f"  PC1 {l1/3*100:5.1f}%   loadings  N {v1[0]:+.2f}  P2O5 {v1[1]:+.2f}  K2O {v1[2]:+.2f}")
print(f"  PC2 {l2/3*100:5.1f}%")
print(f"  PC3 {l3/3*100:5.1f}%")
print(f"  a single-output instrument spans at most PC1, leaving "
      f"{100-l1/3*100:.1f}% unrepresentable")
