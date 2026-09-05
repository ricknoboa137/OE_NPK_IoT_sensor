"""Point the dashboard calibration at the probe-side method.

Firmware facts (firmware/SoilNode/NpkConsole.cpp, commit 58c12c8):

  sensor cal <n|p|k> low  <ref>   reads the probe's own A and B, measures a
  sensor cal <n|p|k> high <ref>   standard, composes a correction and writes
                                  it back into the probe, then verifies
  sensor                          dump the probe's own registers
  cal ...                         the ESP32-side A*raw+B layer, unchanged

Only N, P and K carry a gain register in the probe. Temperature, humidity,
conductivity and pH have offset only, so a span correction for those still has
to happen in the firmware layer - the builder routes each channel to whichever
layer can actually do the job, and says which one it used.

jsonToLine() has no mapping for the "sensor" family, so commands go out as
plain text. handleMqtt() only parses JSON when the payload starts with '{'.
"""
import json, os, sys

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

CAL_DD = "ca11b0a000000020"
CAL_FN = "ca11b0a000000022"
GRP_CAL = "ca11b0a000000011"
TAB = "55ef81d4c950013b"
BTN_PROBE_READ = "ca11b0a000000030"

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

# ---- channel list, labelled with the layer each one lands on ----
by_id[CAL_DD]["options"] = [
    {"label": "Nitrogen (probe)",     "value": "ch:nitrogen",     "type": "str"},
    {"label": "Phosphorus (probe)",   "value": "ch:phosphorus",   "type": "str"},
    {"label": "Potassium (probe)",    "value": "ch:potassium",    "type": "str"},
    {"label": "pH (firmware)",        "value": "ch:ph",           "type": "str"},
    {"label": "Moisture (firmware)",  "value": "ch:moisture",     "type": "str"},
    {"label": "Temperature (firmware)","value": "ch:temperature", "type": "str"},
    {"label": "Conductivity (firmware)","value": "ch:conductivity","type": "str"},
]

# ---- buttons ----
LAYOUT = [
    ("ca11b0a00000002b", "Two-point: LOW",       "act:low",      3, ""),
    ("ca11b0a00000002c", "Two-point: HIGH",      "act:high",     4, ""),
    ("ca11b0a00000002a", "One-point trim",       "act:1p",       5, ""),
    (BTN_PROBE_READ,     "Read probe registers", "act:sensor",   6, ""),
    ("ca11b0a00000002d", "Read firmware A/B",    "act:list",     7, ""),
    ("ca11b0a00000002e", "Reset channel (firmware)", "act:reset",    8, "#b71c1c"),
    ("ca11b0a00000002f", "Reset ALL (firmware)",     "act:resetall", 9, "#b71c1c"),
]

y = 1140
for bid, label, payload, order, bg in LAYOUT:
    node = by_id.get(bid)
    if node is None:
        node = {
            "id": bid, "type": "ui_button", "z": TAB, "group": GRP_CAL,
            "width": 6, "height": 1, "passthru": False, "tooltip": "",
            "color": "", "className": "", "icon": "",
            "payloadType": "str", "topic": "action", "topicType": "str",
            "x": 460, "y": y, "wires": [[CAL_FN]],
        }
        flows.append(node)
        by_id[bid] = node
    node["name"] = label
    node["label"] = label
    node["payload"] = payload
    node["order"] = order
    node["bgcolor"] = bg
    y += 40

CAL_FUNC = r'''// Turn dashboard input into a console command for the SoilNode.
//
// Two calibration layers exist and they are not interchangeable:
//
//   probe side  "sensor cal <n|p|k> low|high <ref>"
//               Reads the gain and offset the probe itself holds, solves a
//               correction against two standards and writes it back, so the
//               probe reports corrected values to anything that reads it.
//               Only N, P and K have a gain register.
//
//   firmware    "cal low|high|1p <channel> <ref>"
//               A*raw+B applied on the ESP32 after reading. Works for every
//               channel, including the four the probe can only offset.
//
// Commands go out as plain text: NpkConsole::jsonToLine has no mapping for
// the "sensor" family, and handleMqtt only parses JSON when the payload
// starts with '{'.

const NUTRIENTS = ["nitrogen", "phosphorus", "potassium"];

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
const onProbe = NUTRIENTS.indexOf(ch) !== -1;

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
    if (onProbe) {
        line = "sensor cal " + ch + " " + act + " " + r;
        note = "probe-side two-point on " + ch;
    } else {
        // the probe has no gain register for this channel
        line = "cal " + act + " " + ch + " " + r;
        note = ch + " has no gain register in the probe, using the firmware layer";
    }
} else if (act === "1p") {
    line = "cal 1p " + ch + " " + r;
    note = "offset-only trim, firmware layer";
} else if (act === "sensor") {
    line = "sensor";
    note = "reading the probe's own registers";
} else if (act === "list") {
    line = "cal";
    note = "reading the firmware-side coefficients";
} else if (act === "reset") {
    line = "cal clear " + ch;
    note = "firmware layer only - probe registers are not touched";
} else if (act === "resetall") {
    line = "cal clear all";
    note = "firmware layer only - probe registers are not touched";
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
print("calibration now drives the probe-side method")
print("channels:", [o["label"] for o in by_id[CAL_DD]["options"]])
print("buttons :", [l for _i, l, _p, _o, _b in LAYOUT])
print("nodes   :", len(flows))
