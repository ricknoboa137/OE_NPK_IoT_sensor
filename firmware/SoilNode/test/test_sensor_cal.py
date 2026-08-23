"""Port of the probe-side two-point solve in NpkConsole::cmdSensor.

The probe already holds a gain and an offset. Rather than overwrite them, the
firmware composes a correction on top of whatever is there:

    g  = (r2 - r1) / (y2 - y1)
    A' = A * g
    B' = r1 - g * (y1 - B)

where r1,r2 are the standards and y1,y2 are what the probe reported with its
current A,B applied. The probe's internal value x never appears, so its
internal scaling need not be known. What IS assumed is that the probe computes
y = A*x + B in that order - the manual calls them factor and offset but never
states the formula, which is why the firmware verifies by re-reading after it
writes.

These tests model a probe with a hidden internal response and check that the
solved pair maps both standards onto their true values.
"""
import math

def solve(a, b, r1, y1, r2, y2):
    """Returns (A', B') or a rejection string, mirroring the C++ guards."""
    if abs(y2 - y1) < 1e-3:      return "probe reported the same value at both standards"
    if not math.isfinite(a) or a == 0.0:  return "current gain unusable"
    g = (r2 - r1) / (y2 - y1)
    a2 = a * g
    b2 = r1 - g * (y1 - b)
    if not math.isfinite(a2) or not math.isfinite(b2) or a2 == 0.0:
        return "solve produced an unusable pair"
    if abs(a2) > 1e3 or abs(b2) > 1e5:
        return "implausible - standards swapped?"
    return (a2, b2)

class Probe:
    """A probe whose internal response to a true concentration is unknown to us."""
    def __init__(self, a, b, gain=1/1.2, off=3.0):
        self.a, self.b = a, b
        self.gain, self.off = gain, off       # hidden: x = c*gain + off
    def x(self, c):      return c * self.gain + self.off
    def report(self, c): return self.a * self.x(c) + self.b

ok = True
def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {detail}")

print("Composing onto the probe's existing coefficients")
for label, (a0, b0) in [("factory A=1 B=0", (1.0, 0.0)),
                        ("already trimmed A=2 B=10", (2.0, 10.0)),
                        ("odd pair A=0.4 B=-25", (0.4, -25.0))]:
    p = Probe(a0, b0)
    r1, r2 = 50.0, 200.0
    y1, y2 = p.report(r1), p.report(r2)
    res = solve(a0, b0, r1, y1, r2, y2)
    if isinstance(res, str):
        check(label, False, f"rejected: {res}")
        continue
    a2, b2 = res
    p.a, p.b = a2, b2
    lo, hi = p.report(r1), p.report(r2)
    mid = p.report(125.0)
    check(f"{label}: low standard", abs(lo - r1) < 1e-3, f"-> {lo:.4f}")
    check(f"{label}: high standard", abs(hi - r2) < 1e-3, f"-> {hi:.4f}")
    check(f"{label}: interpolates", abs(mid - 125.0) < 1e-3, f"-> {mid:.4f}")

print("\nAll three starting points converge on the same absolute calibration")
sols = []
for a0, b0 in [(1.0, 0.0), (2.0, 10.0), (0.4, -25.0)]:
    p = Probe(a0, b0)
    y1, y2 = p.report(50.0), p.report(200.0)
    sols.append(solve(a0, b0, 50.0, y1, 200.0, y2))
check("same A", all(abs(s[0] - sols[0][0]) < 1e-6 for s in sols), f"A={sols[0][0]:.5f}")
check("same B", all(abs(s[1] - sols[0][1]) < 1e-6 for s in sols), f"B={sols[0][1]:.5f}")

print("\nGuards")
check("flat response rejected",
      isinstance(solve(1.0, 0.0, 50.0, 100.0, 200.0, 100.0005), str))
check("zero current gain rejected",
      isinstance(solve(0.0, 0.0, 50.0, 40.0, 200.0, 170.0), str))
check("NaN current gain rejected",
      isinstance(solve(float('nan'), 0.0, 50.0, 40.0, 200.0, 170.0), str))
res = solve(1.0, 0.0, 50.0, 169.67, 200.0, 44.67)      # standards swapped
check("swapped standards give a negative gain",
      not isinstance(res, str) and res[0] < 0,
      f"A={res[0]:.4f}" if not isinstance(res, str) else res)
check("a wildly wrong pair is rejected",
      isinstance(solve(1.0, 0.0, 1.0, 0.0, 2999.0, 0.001), str),
      "(near-flat response over a huge span)")

print("\nOffset written as an integer register - rounding cost")
for b in (-3.6, 0.4, 127.5, -0.5):
    check(f"B={b} rounds to {round(b)}", abs(round(b) - b) <= 0.5)

print("\nALL PASS" if ok else "\nFAILURES PRESENT")
