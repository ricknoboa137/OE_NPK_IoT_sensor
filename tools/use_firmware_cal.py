"""Route all calibration to the microcontroller layer.

Decision: leave the probe in its factory state and correct in the ESP32.

The probe can only offset temperature, humidity, EC and pH (registers
0x0050-0x0053); only N/P/K have a gain as well. NpkCal has no such limit - it
applies A*raw + B to all seven channels - so every channel now gets a full
two-point correction, including pH against buffers 4.00/7.00.

Changes:
  - Two-point LOW/HIGH send "cal low|high <ch> <ref>" for every channel
    (previously "sensor cal <n|p|k> ..." for the nutrients)
  - the "Set probe gain to 1.0" button is removed: it wrote to the probe and
    is only needed for probe-side solving, which we are no longer doing
  - "Read probe registers" stays (read-only diagnostics), as do the backup and
    restore buttons, which remain the safety net for the probe's factory values
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

CAL_DD = "ca11b0a000000020"
CAL_FN = "ca11b0a000000022"
BTN_GAIN1 = "ca11b0a000000031"

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

# ---- channel list: no layer split any more, all seven go to the ESP32 ----
by_id[CAL_DD]["options"] = [
    {"label": "Nitrogen (mg/kg)",   "value": "ch:nitrogen",    "type": "str"},
    {"label": "Phosphorus (mg/kg)", "value": "ch:phosphorus",  "type": "str"},
    {"label": "Potassium (mg/kg)",  "value": "ch:potassium",   "type": "str"},
    {"label": "pH",                 "value": "ch:ph",          "type": "str"},
    {"label": "Moisture (%RH)",     "value": "ch:moisture",    "type": "str"},
    {"label": "Temperature (degC)", "value": "ch:temperature", "type": "str"},
    {"label": "Conductivity",       "value": "ch:conductivity","type": "str"},
]

# ---- remove the probe-gain button and unwire it ----
if BTN_GAIN1 in by_id:
    flows = [n for n in flows if n["id"] != BTN_GAIN1]
    for n in flows:
        for port in n.get("wires", []) or []:
            while BTN_GAIN1 in port:
                port.remove(BTN_GAIN1)
    by_id = {n["id"]: n for n in flows}
    print("removed the probe-gain button")

# renumber so the list has no gaps
for nid, order in {
    "ca11b0a00000002b": 3,   # Two-point LOW
    "ca11b0a00000002c": 4,   # Two-point HIGH
    "ca11b0a00000002a": 5,   # One-point trim
    "ca11b0a000000030": 6,   # Read probe registers
    "ca11b0a00000002d": 7,   # Read firmware A/B
    "ca11b0a00000002e": 8,   # Reset channel
    "ca11b0a00000002f": 9,   # Reset ALL
    "ca11b0a000000040": 10,  # Backup probe registers
    "ca11b0a000000041": 11,  # Restore factory backup
    "ca11b0a000000042": 12,  # List backups
}.items():
    if nid in by_id:
        by_id[nid]["order"] = order

# reset buttons no longer need the "(firmware)" qualifier - everything is firmware
for nid, label in [("ca11b0a00000002e", "Reset channel"),
                   ("ca11b0a00000002f", "Reset ALL")]:
    by_id[nid]["label"] = label
    by_id[nid]["name"] = label

CAL_FUNC = r'''// Turn dashboard input into a console command for the SoilNode.
//
// Every correction is applied in the microcontroller: NpkCal computes
//
//     value = A * raw + B
//
// per channel, where "raw" is whatever the probe reports. The probe is left in
// its factory state deliberately, so it stays a stable input and its own
// constants never enter the arithmetic.
//
// This is why the layer split is gone. The probe can only offset temperature,
// humidity, EC and pH (0x0050-0x0053) and only gives N/P/K a gain; the ESP32
// applies both terms to all seven channels, so pH gets a real two-point span
// correction against buffers 4.00/7.00, which the probe could not do.
//
// Commands go out as plain text: NpkConsole::jsonToLine has no mapping for the
// "sensor" family, and handleMqtt only parses JSON when the payload starts '{'.

const in_ = msg.payload;
const s = (in_ === undefined || in_ === null) ? "" : String(in_);

if (s.indexOf("ch:") === 0) {
    flow.set("calChannel", s.slice(3));
    return null;
}

if (s.indexOf("act:") !== 0) {
    const n = Number(s.replace(",", "."));      // accept 7.00 and 7,00
    if (!isNaN(n)) { flow.set("calRef", n); }
    return null;
}

const act = s.slice(4);
const ch = flow.get("calChannel") || "";
const ref = flow.get("calRef");

const fail = function (why) {
    node.status({ fill: "red", shape: "ring", text: why });
    return [null, { payload: { line: "cannot send: " + why, kind: "error" } }];
};

const needsChannel = (act !== "resetall" && act !== "sensor" && act !== "list");
if (needsChannel && !ch) { return fail("choose a channel first"); }

const needsRef = (act === "1p" || act === "low" || act === "high");
if (needsRef && (ref === undefined || ref === null || isNaN(ref))) {
    return fail("enter a reference value first");
}

const r = String(ref);
let line = "";
let note = "";

if (act === "low" || act === "high") {
    line = "cal " + act + " " + ch + " " + r;
    note = "two-point step, solved and stored in the ESP32";
} else if (act === "1p") {
    line = "cal 1p " + ch + " " + r;
    note = "offset-only trim, keeps the current gain";
} else if (act === "sensor") {
    line = "sensor";
    note = "read-only: the probe's own registers, left at factory values";
} else if (act === "list") {
    line = "cal";
    note = "the coefficients in use";
} else if (act === "reset") {
    line = "cal clear " + ch;
    note = "back to A=1, B=0 for this channel";
} else if (act === "resetall") {
    line = "cal clear all";
    note = "back to A=1, B=0 on every channel";
} else {
    return fail("unknown action " + act);
}

node.status({ fill: "blue", shape: "dot", text: line });

return [
    { topic: "NPKcommand", payload: line },
    { payload: { line: "> " + line + "\n  (" + note + ")", kind: "sent" } }
];
'''
by_id[CAL_FN]["func"] = CAL_FUNC

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("all calibration now targets the microcontroller; nodes: %d" % len(flows))
