"""Bring the flow up to the SoilNode 2.1.0 firmware.

Firmware facts this is built against (firmware/SoilNode):
  topics   NPKdata / NPKstatus (retained) / NPKcommand / NPKreply   NpkConfig.h
  payload  Humidity Temperature Conductivity PH Nitrogen Phosphorus
           Potassium + ok                                           SoilNode.ino
  console  accepts JSON on NPKcommand, normalised to the text form,
           replies as plain text on NPKreply                        NpkConsole.cpp
  cal      value = A*raw + B; cal_set / cal_1p / cal_low / cal_high /
           cal_reset / cal_list; channel keys are the `key` column
           of NPK_CHANNELS                                          NpkCal.h

Adds:
  1. the Conductivity channel end to end (gauge, chart, storage)
  2. a Calibration dashboard tab driving the console over MQTT
  3. a live log of commands sent and replies received
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

TAB = "55ef81d4c950013b"
BROKER = "6c414a6c07090bf9"          # the broker the NPKdata input already uses
SQLITE_DB = "e9b358432d3979d4"
QUERY_NODE = "6c521fc6f2276524"      # feeds every ToPlotData
RANGE_FN = "aa11bb22cc33dd02"
INSERT_FN = "06fee8be07ade0d1"
CREATE_INJECT = "8ca9efddfa25bc49"
GRP_VARIABLES = "117f0ad31ac9c6f9"   # Lectures tab
GRP_PARAMETER = "b3b2ba7659a6611a"   # Charts tab

# firmware channel keys, in NpkChannelId order
CHANNELS = [
    ("moisture",     "Humidity",     "%RH"),
    ("temperature",  "Temperature",  "degC"),
    ("conductivity", "Conductivity", "us/cm"),
    ("ph",           "PH",           "pH"),
    ("nitrogen",     "Nitrogen",     "mg/kg"),
    ("phosphorus",   "Phosphorus",   "mg/kg"),
    ("potassium",    "Potassium",    "mg/kg"),
]

# ---------------------------------------------------------------------------
# 1. Conductivity + ok through the storage path
# ---------------------------------------------------------------------------
by_id[CREATE_INJECT]["topic"] = (
    "CREATE TABLE IF NOT EXISTS NPKv1 ("
    "timestamp INTEGER, ts_utc TEXT, "
    "humidity REAL, temperature REAL, conductivity REAL, PH REAL, "
    "N REAL, P REAL, K REAL, ok INTEGER);")

INSERT_FUNC = r'''const p = msg.payload;

if (p === null || typeof p !== "object" || Array.isArray(p)) {
    node.warn("NPKdata payload is not an object, ignoring: " + JSON.stringify(p));
    return null;
}

// null rather than a broken statement when a field is missing or non-numeric
const num = function (v) {
    if (v === undefined || v === null || v === "") { return null; }
    const n = Number(v);
    return isNaN(n) ? null : n;
};

const now = new Date();

msg.params = {
    $ts: Math.floor(now.getTime() / 1000),                        // unix seconds, UTC
    $ts_utc: now.toISOString().slice(0, 19).replace("T", " "),    // human readable, UTC
    $humidity: num(p.Humidity),
    $temperature: num(p.Temperature),
    $conductivity: num(p.Conductivity),   // 7th channel, SoilNode 2.1.0
    $ph: num(p.PH),
    $n: num(p.Nitrogen),
    $p: num(p.Phosphorus),
    $k: num(p.Potassium),
    // firmware sets ok=false when the sweep was partial and some values are
    // carried over from the previous reading
    $ok: (p.ok === undefined) ? null : (p.ok ? 1 : 0)
};

node.status({ fill: p.ok === false ? "yellow" : "green", shape: "dot",
              text: msg.params.$ts_utc + (p.ok === false ? " partial" : "") });
return msg;
'''
by_id[INSERT_FN]["func"] = INSERT_FUNC

by_id["a1b2c3d4e5f60001"]["sql"] = (
    "INSERT INTO NPKv1 (timestamp, ts_utc, humidity, temperature, conductivity, "
    "PH, N, P, K, ok) VALUES ($ts, $ts_utc, $humidity, $temperature, $conductivity, "
    "$ph, $n, $p, $k, $ok)")

# range query must select the new column too
fn = by_id[RANGE_FN]
fn["func"] = fn["func"].replace(
    'const COLS = "humidity, temperature, PH, N, P, K";',
    'const COLS = "humidity, temperature, conductivity, PH, N, P, K";'
).replace(
    ' avg(humidity) as humidity, avg(temperature) as temperature, avg(PH) as PH," +',
    ' avg(humidity) as humidity, avg(temperature) as temperature," +'
    '\n        " avg(conductivity) as conductivity, avg(PH) as PH," +'
)

# ---------------------------------------------------------------------------
# 2. Conductivity gauge and chart
# ---------------------------------------------------------------------------
EC_GAUGE = "ca11b0a000000001"
EC_CHART = "ca11b0a000000002"
EC_PLOT = "ca11b0a000000003"

if EC_GAUGE not in by_id:
    flows.append({
        "id": EC_GAUGE, "type": "ui_gauge", "z": TAB, "name": "EC",
        "group": GRP_VARIABLES, "order": 4, "width": 0, "height": 0,
        "gtype": "gage", "title": "Conductivity", "label": "uS/cm",
        "format": "{{msg.payload.Conductivity}}",
        "min": 0, "max": "3000",
        "colors": ["#00b500", "#e6e600", "#ca3838"],
        "seg1": "", "seg2": "", "diff": False, "className": "",
        "x": 950, "y": 440, "wires": [],
    })
    # the NPKdata input fans out to every gauge
    by_id["b4c9b453f39b484d"]["wires"][0].append(EC_GAUGE)

if EC_CHART not in by_id:
    flows.append({
        "id": EC_CHART, "type": "ui_chart", "z": TAB, "name": "",
        "group": GRP_PARAMETER, "order": 4, "width": 0, "height": 0,
        "label": "Conductivity [uS/cm]", "chartType": "line", "legend": "false",
        "xformat": "auto", "interpolate": "linear", "nodata": "", "dot": False,
        "ymin": "", "ymax": "", "removeOlder": 730, "removeOlderPoints": "",
        "removeOlderUnit": "86400", "cutout": 0, "useOneColor": False,
        "useUTC": False,
        "colors": ["#1f77b4", "#aec7e8", "#ff7f0e", "#2ca02c", "#98df8a",
                   "#d62728", "#ff9896", "#9467bd", "#c5b0d5"],
        "outputs": 1, "useDifferentColor": False, "className": "",
        "x": 1070, "y": 860, "wires": [[]],
    })

PLOT_FUNC = '''const rows = Array.isArray(msg.payload) ? msg.payload : [];

const out = [{
    series: ["Conductivity"],
    data: [[]],
    labels: [""]
}];

for (const item of rows) {
    if (item.conductivity === null || item.conductivity === undefined) { continue; }
    out[0].data[0].push({
        x: item.timestamp * 1000,   // stored as unix seconds, chart wants ms
        y: item.conductivity
    });
}

msg.payload = out;
return msg;
'''
if EC_PLOT not in by_id:
    flows.append({
        "id": EC_PLOT, "type": "function", "z": TAB,
        "name": "ToPlotData conductivity", "func": PLOT_FUNC,
        "outputs": 1, "timeout": 0, "noerr": 0, "initialize": "", "finalize": "",
        "libs": [], "x": 870, "y": 860, "wires": [[EC_CHART]],
    })
    by_id[QUERY_NODE]["wires"][0].append(EC_PLOT)

# ---------------------------------------------------------------------------
# 3. Calibration tab
# ---------------------------------------------------------------------------
UI_TAB_CAL = "ca11b0a000000010"
GRP_CAL = "ca11b0a000000011"
GRP_LOG = "ca11b0a000000012"

flows.append({
    "id": UI_TAB_CAL, "type": "ui_tab", "name": "Calibration",
    "icon": "dashboard", "order": 3, "disabled": False, "hidden": False,
})
flows.append({
    "id": GRP_CAL, "type": "ui_group", "name": "Calibrate", "tab": UI_TAB_CAL,
    "order": 1, "disp": True, "width": 6, "collapse": False, "className": "",
})
flows.append({
    "id": GRP_LOG, "type": "ui_group", "name": "Node", "tab": UI_TAB_CAL,
    "order": 2, "disp": True, "width": 6, "collapse": False, "className": "",
})

CAL_DD = "ca11b0a000000020"
CAL_REF = "ca11b0a000000021"
CAL_FN = "ca11b0a000000022"
CAL_OUT = "ca11b0a000000023"
CAL_REPLY_IN = "ca11b0a000000024"
CAL_LOG_FN = "ca11b0a000000025"
CAL_LOG_UI = "ca11b0a000000026"
CAL_STATUS_IN = "ca11b0a000000027"
CAL_STATUS_FN = "ca11b0a000000028"
CAL_STATUS_UI = "ca11b0a000000029"

flows.append({
    "id": CAL_DD, "type": "ui_dropdown", "z": TAB, "name": "cal channel",
    "label": "Channel", "tooltip": "Which channel to calibrate",
    "place": "Select channel", "group": GRP_CAL, "order": 1,
    "width": 6, "height": 1, "passthru": True, "multiple": False,
    "options": [{"label": "%s (%s)" % (key, unit), "value": "ch:" + key, "type": "str"}
                for key, _json, unit in CHANNELS],
    "payload": "", "topic": "channel", "topicType": "str", "className": "",
    "x": 460, "y": 1060, "wires": [[CAL_FN]],
})

flows.append({
    "id": CAL_REF, "type": "ui_text_input", "z": TAB, "name": "reference",
    "label": "Reference value", "tooltip": "Known value of the standard, e.g. 7.00 for pH buffer",
    "group": GRP_CAL, "order": 2, "width": 6, "height": 1,
    "passthru": True, "mode": "number", "delay": "600", "topic": "ref",
    "sendOnBlur": True, "className": "", "topicType": "str",
    "x": 460, "y": 1100, "wires": [[CAL_FN]],
})

BUTTONS = [
    ("ca11b0a00000002a", "One-point trim",  "act:1p",       3),
    ("ca11b0a00000002b", "Two-point: LOW",  "act:low",      4),
    ("ca11b0a00000002c", "Two-point: HIGH", "act:high",     5),
    ("ca11b0a00000002d", "Read coefficients", "act:list",   6),
    ("ca11b0a00000002e", "Reset channel",   "act:reset",    7),
    ("ca11b0a00000002f", "Reset ALL",       "act:resetall", 8),
]
y = 1140
for bid, label, payload, order in BUTTONS:
    flows.append({
        "id": bid, "type": "ui_button", "z": TAB, "name": label,
        "group": GRP_CAL, "order": order, "width": 6, "height": 1,
        "passthru": False, "label": label, "tooltip": "", "color": "",
        "bgcolor": "#b71c1c" if "reset" in payload else "",
        "className": "", "icon": "",
        "payload": payload, "payloadType": "str",
        "topic": "action", "topicType": "str",
        "x": 460, "y": y, "wires": [[CAL_FN]],
    })
    y += 40

CAL_FUNC = r'''// Turn dashboard input into a JSON command for the SoilNode console.
//
// The firmware accepts either text ("cal low ph 4.00") or JSON on NPKcommand
// and normalises JSON into the text form, so JSON is the safer wire format -
// no quoting or decimal-separator surprises. See NpkConsole::jsonToLine.
//
// Selections arrive on three routes and are remembered in flow context, so the
// buttons work whatever order things are touched in:
//     "ch:<key>"   from the channel dropdown
//     a number     from the reference input
//     "act:<verb>" from a button

const in_ = msg.payload;
const s = (in_ === undefined || in_ === null) ? "" : String(in_);

if (s.indexOf("ch:") === 0) {
    flow.set("calChannel", s.slice(3));
    return null;                        // a selection is not an action
}

if (s.indexOf("act:") !== 0) {
    // reference input: accept both 7.00 and 7,00
    const n = Number(s.replace(",", "."));
    if (!isNaN(n)) { flow.set("calRef", n); }
    return null;
}

const act = s.slice(4);
const ch = flow.get("calChannel") || "";
const ref = flow.get("calRef");

const fail = function (why) {
    node.status({ fill: "red", shape: "ring", text: why });
    return { payload: { line: "cannot send: " + why, kind: "error" } };
};

if (act !== "resetall" && !ch) {
    return [null, fail("choose a channel first")];
}
if ((act === "1p" || act === "low" || act === "high") &&
    (ref === undefined || ref === null || isNaN(ref))) {
    return [null, fail("enter a reference value first")];
}

let cmd;
if (act === "1p")            { cmd = { cmd: "cal_1p",    ch: ch, ref: ref }; }
else if (act === "low")      { cmd = { cmd: "cal_low",   ch: ch, ref: ref }; }
else if (act === "high")     { cmd = { cmd: "cal_high",  ch: ch, ref: ref }; }
else if (act === "list")     { cmd = { cmd: "cal_list" }; }
else if (act === "reset")    { cmd = { cmd: "cal_reset", ch: ch }; }
else if (act === "resetall") { cmd = { cmd: "cal_reset", ch: "all" }; }
else                         { return [null, fail("unknown action " + act)]; }

const out = { topic: "NPKcommand", payload: JSON.stringify(cmd) };

node.status({ fill: "blue", shape: "dot", text: out.payload });

// second output feeds the on-screen log so the operator sees what was sent
return [out, { payload: { line: "> " + out.payload, kind: "sent" } }];
'''

flows.append({
    "id": CAL_FN, "type": "function", "z": TAB, "name": "build cal command",
    "func": CAL_FUNC, "outputs": 2, "timeout": 0, "noerr": 0,
    "initialize": "", "finalize": "", "libs": [],
    "x": 700, "y": 1120, "wires": [[CAL_OUT], [CAL_LOG_FN]],
})

flows.append({
    "id": CAL_OUT, "type": "mqtt out", "z": TAB, "name": "NPKcommand",
    "topic": "NPKcommand", "qos": "0", "retain": "false",
    "respTopic": "", "contentType": "", "userProps": "", "correl": "",
    "expiry": "", "broker": BROKER,
    "x": 930, "y": 1100, "wires": [],
})

flows.append({
    "id": CAL_REPLY_IN, "type": "mqtt in", "z": TAB, "name": "NPKreply",
    "topic": "NPKreply", "qos": "0", "datatype": "utf8", "broker": BROKER,
    "nl": False, "rap": True, "rh": 0, "inputs": 0,
    "x": 460, "y": 1400, "wires": [[CAL_LOG_FN]],
})

LOG_FUNC = r'''// Rolling log of commands sent and replies received.
// Replies are multi-line fixed-width text from the firmware console
// (see NpkConsole::listCalibration), so they are shown verbatim in a <pre>.

const MAX_LINES = 120;

let entry, kind;
if (msg.payload && typeof msg.payload === "object" && msg.payload.line !== undefined) {
    entry = msg.payload.line;              // from the command builder
    kind = msg.payload.kind || "sent";
} else {
    entry = String(msg.payload).replace(/\r/g, "");   // reply from the node
    kind = "reply";
}

const stamp = new Date().toTimeString().slice(0, 8);

let lines = flow.get("calLog") || [];
for (const raw of entry.split("\n")) {
    if (raw.trim() === "" && kind === "reply") { continue; }
    lines.push({ t: stamp, k: kind, s: raw });
}
if (lines.length > MAX_LINES) { lines = lines.slice(lines.length - MAX_LINES); }
flow.set("calLog", lines);

const esc = function (s) {
    return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
};
const colour = { sent: "#1565c0", reply: "#222", error: "#b71c1c" };

// newest first, so the latest reply is visible without scrolling
const html = lines.slice().reverse().map(function (l) {
    return '<div style="color:' + (colour[l.k] || "#222") + '">' +
           '<span style="opacity:.55">' + l.t + '</span>  ' + esc(l.s) + '</div>';
}).join("");

msg.payload = '<pre style="margin:0;font-size:12px;line-height:1.35;' +
              'white-space:pre-wrap;word-break:break-word">' + html + '</pre>';
node.status({ fill: "grey", shape: "dot", text: lines.length + " lines" });
return msg;
'''

flows.append({
    "id": CAL_LOG_FN, "type": "function", "z": TAB, "name": "cal log",
    "func": LOG_FUNC, "outputs": 1, "timeout": 0, "noerr": 0,
    "initialize": "", "finalize": "", "libs": [],
    "x": 700, "y": 1400, "wires": [[CAL_LOG_UI]],
})

flows.append({
    "id": CAL_LOG_UI, "type": "ui_template", "z": TAB, "group": GRP_LOG,
    "name": "console log", "order": 2, "width": 6, "height": 8,
    "format": '<div style="height:100%;overflow:auto" ng-bind-html="msg.payload"></div>',
    "storeOutMessages": True, "fwdInMessages": True, "resendOnRefresh": True,
    "templateScope": "local", "className": "",
    "x": 930, "y": 1400, "wires": [[]],
})

# ---- node status (retained topic, so it lands as soon as the flow starts) ----
flows.append({
    "id": CAL_STATUS_IN, "type": "mqtt in", "z": TAB, "name": "NPKstatus",
    "topic": "NPKstatus", "qos": "0", "datatype": "utf8", "broker": BROKER,
    "nl": False, "rap": True, "rh": 0, "inputs": 0,
    "x": 460, "y": 1340, "wires": [[CAL_STATUS_FN]],
})

STATUS_FUNC = r'''// NPKstatus is retained: "online" or "sensor-unreachable" (SoilNode.ino).
const s = String(msg.payload);
const stamp = new Date().toTimeString().slice(0, 8);

if (s === "online") {
    msg.payload = "sensor online · " + stamp;
    node.status({ fill: "green", shape: "dot", text: "online" });
} else if (s === "sensor-unreachable") {
    msg.payload = "SENSOR UNREACHABLE · " + stamp;
    node.status({ fill: "red", shape: "dot", text: "unreachable" });
} else {
    msg.payload = s + " · " + stamp;
    node.status({ fill: "grey", shape: "dot", text: s });
}
return msg;
'''
flows.append({
    "id": CAL_STATUS_FN, "type": "function", "z": TAB, "name": "node status",
    "func": STATUS_FUNC, "outputs": 1, "timeout": 0, "noerr": 0,
    "initialize": "", "finalize": "", "libs": [],
    "x": 700, "y": 1340, "wires": [[CAL_STATUS_UI]],
})
flows.append({
    "id": CAL_STATUS_UI, "type": "ui_text", "z": TAB, "group": GRP_LOG,
    "name": "status", "order": 1, "width": 6, "height": 1,
    "label": "", "format": "{{msg.payload}}", "layout": "col-center",
    "className": "", "style": False, "font": "", "fontSize": 14,
    "color": "#000000",
    "x": 930, "y": 1340, "wires": [],
})

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("flow updated: %d nodes" % len(flows))
