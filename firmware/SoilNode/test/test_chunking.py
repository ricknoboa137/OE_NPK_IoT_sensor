"""Port of NpkChunkedPrint, checked against the outputs it has to carry.

The acceptance criterion is that no console reply is ever truncated over MQTT.
Raising the buffer cannot deliver that on its own: "scan" output is unbounded,
and this probe answers at every one of 65536 addresses. So output is split
across as many NPKreply messages as it takes, at line boundaries, with every
part except the last ending in a continuation marker.

What these tests check:
  - reassembling the parts reproduces the input byte for byte
  - only the final part lacks the marker
  - no line is ever split across two parts
  - every published part fits the MQTT buffer
"""
import sys

MARKER = "[continues]"
MARKER_SIZEOF = len(MARKER) + 1        # sizeof() in C includes the NUL
MAX_LINE_HELD = 192

class Chunked:
    """Mirrors NpkChunkedPrint: same buffer arithmetic, same split rule."""
    def __init__(self, cap):
        self.cap = cap
        self.usable = cap - MARKER_SIZEOF - 1 if cap > MARKER_SIZEOF + 1 else cap
        self.buf = []
        self.last_nl = 0
        self.parts = []
        self.dropped = 0

    def _flush_part(self):
        if not self.buf:
            return
        split = self.last_nl if self.last_nl > 0 else len(self.buf)
        tail_len = len(self.buf) - split
        if tail_len >= MAX_LINE_HELD:
            split = len(self.buf)
            tail_len = 0
        tail = self.buf[split:split + tail_len]
        self.parts.append(''.join(self.buf[:split]) + MARKER)
        self.buf = list(tail)
        self.last_nl = 0
        for i, c in enumerate(self.buf):
            if c == '\n':
                self.last_nl = i + 1

    def write(self, ch):
        if len(self.buf) + 1 >= self.usable:
            self._flush_part()
        if len(self.buf) + 1 >= self.usable:
            self.dropped += 1
            return 0
        self.buf.append(ch)
        if ch == '\n':
            self.last_nl = len(self.buf)
        return 1

    def print(self, text):
        for ch in text:
            self.write(ch)

    def finish(self):
        if self.buf:
            self.parts.append(''.join(self.buf))
            self.buf = []

def reassemble(parts):
    out = []
    for i, p in enumerate(parts):
        if i < len(parts) - 1:
            assert p.endswith(MARKER), f"part {i} is missing the continuation marker"
            out.append(p[:-len(MARKER)])
        else:
            assert not p.endswith(MARKER), "the final part must not be marked as continuing"
            out.append(p)
    return ''.join(out)

# --- the real outputs this has to carry -------------------------------------
def sensor_dump():
    L = []
    L.append("\r\nSensor-side calibration (stored in the probe, not the ESP32)\r\n")
    for reg, name, val, dflt in ((0x22, "conductivity factor", 0, 0),
                                 (0x23, "salinity factor", 55, 55),
                                 (0x24, "TDS factor", 50, 50)):
        L.append(f"  0x{reg:04X}  {name:<20} {val:6d}   factory default {dflt}\r\n")
    L.append("\r\n")
    for reg, name in ((0x50, "temperature offset"), (0x51, "humidity offset"),
                      (0x52, "conductivity offset"), (0x53, "pH offset")):
        L.append(f"  0x{reg:04X}  {name:<20} raw {0:6d}  -> {0.0:.2f}\r\n")
    for reg, key in ((0x04E8, "n"), (0x04F2, "p"), (0x04FC, "k")):
        L.append(f"  0x{reg:04X}  {key} factor {0.0:.5f}   offset {0}\r\n")
    L.append("\r\n")
    for line in ("The manual documents factory defaults only for 0x0022-0x0024.",
                 "For the offsets and the N/P/K factors it states none, so what",
                 "they read here is whatever the unit shipped with - most likely",
                 "0 offsets and unit gains, but that is not promised anywhere.",
                 "",
                 "  sensor cal <n|p|k> low  <ref>          two-point solve against",
                 "  sensor cal <n|p|k> high <ref>          the probe's own A and B",
                 "  sensor offset <temp|hum|ec|ph> <raw>   write an offset register",
                 "  sensor factor <n|p|k> <value>          write the gain float",
                 "  sensor npk    <n|p|k> <mg/kg>          write a measured value"):
        L.append(line + "\r\n")
    return ''.join(L)

CHANNELS = ["moisture", "temperature", "conductivity", "ph",
            "nitrogen", "phosphorus", "potassium"]

def cal_table():
    L = ["\r\n", f"{'channel':<14} {'A (gain)':>12} {'B (offset)':>12}   state\r\n"]
    for c in CHANNELS:
        L.append(f"{c:<14} {1.0:>12.5f} {0.0:>12.5f}   default\r\n")
    L.append("\r\n")
    return ''.join(L)

def cal_json():
    body = ",".join(f'"{c}":{{"a":{1.0:.5f},"b":{0.0:.5f},"state":"default"}}'
                    for c in CHANNELS)
    return "{" + body + "}\r\n"

def cal_export():
    L = ["\r\n# SoilNode calibration - paste back to restore\r\n"]
    for c in CHANNELS:
        L.append(f"cal set {c} {1.0:.5f} {0.0:.5f}\r\n")
    L.append("\r\n")
    return ''.join(L)

def scan_output(n):
    L = [f"Scanning 0x0000..0x{n-1:04X} at 4800 baud, slave 0x01, non-zero only\r\n",
         f"{n} registers, roughly {n//20} s\r\n"]
    for a in range(n):
        L.append(f"  0x{a:04X} = {a:5d}  (0x{a:04X})  signed {a:6d}   "
                 f"/10 {a/10:.1f}  /100 {a/100:.2f}\r\n")
    L.append(f"Scan finished: {n} answered, {n} non-zero.\r\n")
    return ''.join(L)

CAP = 1280 - 64          # kReplyCap

ok = True
def check(label, cond, detail=""):
    global ok
    ok &= bool(cond)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label} {detail}")

def run(name, text, cap=CAP, expect_line_boundaries=True):
    s = Chunked(cap)
    s.print(text)
    s.finish()
    rebuilt = reassemble(s.parts)
    check(f"{name}: nothing dropped", s.dropped == 0, f"({len(text)} B)")
    check(f"{name}: reassembles exactly", rebuilt == text,
          f"-> {len(s.parts)} part(s)")
    check(f"{name}: every part fits the buffer",
          all(len(p) + 1 <= cap for p in s.parts),
          f"largest {max(len(p) for p in s.parts)} B of {cap}")
    # a line must never be broken across two parts
    orig_lines = text.split('\n')
    rebuilt_lines = rebuilt.split('\n')
    check(f"{name}: line count preserved", len(orig_lines) == len(rebuilt_lines))
    broken = [i + 1 for i, p in enumerate(s.parts[:-1])
              if p[:-len(MARKER)] and not p[:-len(MARKER)].endswith('\n')]
    if len(s.parts) > 1 and expect_line_boundaries:
        check(f"{name}: every split lands on a line boundary",
              not broken, f"({len(s.parts) - 1} splits)" if not broken
                          else f"broken at parts {broken}")
    return s

print("Single-message replies keep today's behaviour")
s = run("cal table", cal_table())
check("cal table is one part, unmarked", len(s.parts) == 1)
s = run("cal json", cal_json())
check("cal json is one part - it must be parseable whole", len(s.parts) == 1,
      f"({len(cal_json())} B)")
s = run("cal export", cal_export())
check("cal export is one part", len(s.parts) == 1)

print("\nThe reply that was observed truncated")
s = run("sensor dump", sensor_dump())
print(f"       sensor dump is {len(sensor_dump())} B against a {CAP} B buffer")

print("\nUnbounded output - the case a bigger buffer could never fix")
for n in (100, 1000, 8192):
    s = run(f"scan nz {n} regs", scan_output(n))
    print(f"       {n} registers -> {len(scan_output(n))} B in {len(s.parts)} parts")

print("\nEdges")
s = run("empty-ish", "\r\n")
s = Chunked(CAP); s.finish()
check("no output publishes nothing", len(s.parts) == 0)
# A line longer than the hold buffer cannot be carried across a split, so it
# IS cut mid-line - deliberately. What must still hold is that no character is
# lost. Nothing this firmware prints comes near 192 characters.
long_line = "x" * 5000 + "\r\n"
s = run("one absurd 5000-char line", long_line, expect_line_boundaries=False)
check("a line too long to hold back is cut, but not truncated",
      reassemble(s.parts) == long_line, f"{len(s.parts)} parts, all bytes present")
longest_real = max(len(l) for l in (sensor_dump() + cal_table() +
                                    scan_output(16)).split('\n'))
check("the longest line this firmware actually prints fits the hold buffer",
      longest_real < MAX_LINE_HELD, f"{longest_real} B of {MAX_LINE_HELD}")

print("\nALL PASS" if ok else "\nFAILURES PRESENT")
sys.exit(0 if ok else 1)
