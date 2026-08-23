"""Port of the C++ validation predicates, exercised against the cases that matter."""
import math, struct

# --- npkCoeffPlausible ------------------------------------------------------
def coeff_plausible(a, b):
    if not math.isfinite(a) or not math.isfinite(b): return "coefficients must be finite"
    if a == 0.0:        return "A of zero would flatten the channel"
    if abs(a) < 1e-3:   return "A below 0.001 collapses the channel"
    if abs(a) > 1e3:    return "A above 1000 implausible"
    if abs(b) > 1e5:    return "B above 100000 implausible"
    return None

# --- npkInRange -------------------------------------------------------------
CH = {  # name: (lo, hi)
    "moisture":     (0.0, 100.0),
    "temperature":  (-40.0, 80.0),
    "conductivity": (0.0, 20000.0),
    "ph":           (0.0, 14.0),
    "nitrogen":     (0.0, 2999.0),
}
def in_range(ch, v):
    lo, hi = CH[ch]
    return math.isfinite(v) and lo <= v <= hi

# --- readFloat --------------------------------------------------------------
def read_float(hi_word, lo_word):
    bits = (hi_word << 16) | lo_word
    v = struct.unpack(">f", struct.pack(">I", bits))[0]
    if not math.isfinite(v):                return None, "not a valid float"
    if v != 0.0 and abs(v) < 1e-6:          return None, "denormal"
    return v, None

ok = True
def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {detail}")

print("Coefficient plausibility")
check("A=1  B=0 accepted",            coeff_plausible(1.0, 0.0) is None)
check("A=0.94 B=-0.06 accepted",      coeff_plausible(0.94044, -0.0627) is None)
check("A=10 scale fix accepted",      coeff_plausible(10.0, 0.0) is None)
check("A=0.1 scale fix accepted",     coeff_plausible(0.1, 0.0) is None)
check("A=100 pH scale fix accepted",  coeff_plausible(100.0, 0.0) is None)
check("A=-1.33 inverted accepted",    coeff_plausible(-1.3333, 90.0) is None)
check("A=0 rejected",                 coeff_plausible(0.0, 0.0) is not None)
check("A=nan rejected",               coeff_plausible(float('nan'), 0.0) is not None)
check("A=inf rejected",               coeff_plausible(float('inf'), 0.0) is not None)
check("B=nan rejected",               coeff_plausible(1.0, float('nan')) is not None)
check("A=1e-30 denormal rejected",    coeff_plausible(1e-30, 0.0) is not None)
check("A=1e20 rejected",              coeff_plausible(1e20, 0.0) is not None)
check("A=5000 typo rejected",         coeff_plausible(5000.0, 0.0) is not None)
check("B=1e9 rejected",               coeff_plausible(1.0, 1e9) is not None)

print("\nPost-calibration range check (the gap that existed before)")
raw = 46.4                                   # a perfectly good moisture reading
check("A=1000 -> 46400 rejected",     not in_range("moisture", 1000.0*raw + 0))
check("  and A=1000 never stored",    coeff_plausible(1000.0, 0.0) is None,
      "(within bounds, so the range check is what stops it)")
check("A=2 -> 92.8 accepted",         in_range("moisture", 2.0*raw))
check("A=3 -> 139.2 rejected",        not in_range("moisture", 3.0*raw))
check("B=-50 -> -3.6 rejected",       not in_range("moisture", raw - 50))
check("temp -10 C in range",          in_range("temperature", -10.1))
check("temp -50 C rejected",          not in_range("temperature", -50.0))
check("conductivity 0 accepted",      in_range("conductivity", 0.0),
      "(this unit always reads 0)")
check("N 2999 accepted",              in_range("nitrogen", 2999.0))
check("N 4090 rejected",              not in_range("nitrogen", 4090.0),
      "(the value that started this)")

print("\nWhy there is no static 'suspect coefficients' check")
def endpoint_heuristic(ch, a, b):
    lo, hi = CH[ch]
    return not in_range(ch, a*lo + b) and not in_range(ch, a*hi + b)
# Both directions are broken, which is why this was removed rather than shipped.
check("misses a wild gain: A=900 on pH not flagged",
      not endpoint_heuristic("ph", 900.0, 0.0),
      "(pH lo is 0, so any pure gain maps 0->0 and looks fine)")
check("same blind spot on moisture, N, P, K",
      not endpoint_heuristic("moisture", 900.0, 0.0) and
      not endpoint_heuristic("nitrogen", 900.0, 0.0),
      "(every channel but temperature has lo = 0)")
check("stricter both-ends rule would reject a legitimate A=1.1",
      not in_range("moisture", 1.1*100.0),
      "(maps 100 %RH to 110, so 'both ends in range' false-positives)")

print("\nreadFloat validation of probe registers")
v, err = read_float(0x3F80, 0x0000); check("0x3F800000 -> 1.0", v == 1.0 and err is None, f"got {v}")
v, err = read_float(0x3F93, 0x3333); check("0x3F933333 -> ~1.15", err is None and abs(v-1.15) < 1e-6, f"got {v}")
v, err = read_float(0xFFFF, 0xFFFF); check("all-ones -> rejected as NaN", v is None, f"({err})")
v, err = read_float(0x7F80, 0x0000); check("+inf rejected", v is None, f"({err})")
v, err = read_float(0x0000, 0x0001); check("denormal rejected", v is None, f"({err})")
v, err = read_float(0x0000, 0x0000); check("0.0 accepted", v == 0.0 and err is None)

print("\nALL PASS" if ok else "\nFAILURES PRESENT")
