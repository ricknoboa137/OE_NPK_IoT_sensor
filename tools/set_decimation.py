"""Replace fixed-interval bucketing with fixed-N averaging.

Every N consecutive readings collapse to one point (N = 1 raw, 5, or 10), so
resolution no longer degrades as the range widens. Adds an "All data" range so
the January archive is reachable, and a second dropdown for N.
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

TAB = "55ef81d4c950013b"
BUTTONS_GROUP = "d91c5f0cac293037"
RANGE_FN = "aa11bb22cc33dd02"
COUNT_FN = "aa11bb22cc33dd03"
AVG_DROPDOWN = "aa11bb22cc33dd05"

# ---- range dropdown: add "All data" ----
by_id["aa11bb22cc33dd01"]["options"] = [
    {"label": "Last 7 days",   "value": "7",   "type": "str"},
    {"label": "Last 15 days",  "value": "15",  "type": "str"},
    {"label": "Last month",    "value": "30",  "type": "str"},
    {"label": "Last 3 months", "value": "90",  "type": "str"},
    {"label": "All data",      "value": "all", "type": "str"},
]

# ---- new dropdown: averaging factor ----
flows.append({
    "id": AVG_DROPDOWN,
    "type": "ui_dropdown",
    "z": TAB,
    "name": "averaging",
    "label": "Averaging",
    "tooltip": "How many readings collapse into one plotted point",
    "place": "Select averaging",
    "group": BUTTONS_GROUP,
    "order": 1,
    "width": 0,
    "height": 0,
    "passthru": True,
    "multiple": False,
    "options": [
        {"label": "Raw (every reading)", "value": "avg:1",  "type": "str"},
        {"label": "Average of 5",        "value": "avg:5",  "type": "str"},
        {"label": "Average of 10",       "value": "avg:10", "type": "str"},
    ],
    "payload": "",
    "topic": "averaging",
    "topicType": "str",
    "className": "",
    "x": 480,
    "y": 540,
    "wires": [[RANGE_FN]],
})

# ---- query builder ----
RANGE_FUNC = r'''// Build the chart query from two independent selections, each remembered in
// flow context so either dropdown (or the Refresh button) can trigger a reload.
//
//   range     : 7 / 15 / 30 / 90 days, or "all"
//   averaging : N consecutive readings per plotted point (1 = raw)
//
// Averaging is by row count, not by time bucket, so widening the range does not
// coarsen the trace - it only adds points.

const RANGES = ["7", "15", "30", "90", "all"];
const in_ = String(msg.payload === undefined ? "" : msg.payload);

if (in_.indexOf("avg:") === 0) {
    const n = parseInt(in_.slice(4), 10);
    if (!isNaN(n) && n > 0) { flow.set("avgN", n); }
}
else if (RANGES.indexOf(in_) !== -1) {
    flow.set("range", in_);
}
// anything else (the Refresh button) just reuses what is stored

const range = flow.get("range") || "7";
const N = flow.get("avgN") || 5;

const where = (range === "all")
    ? ""
    : " where timestamp >= strftime('%s','now') - " + (parseInt(range, 10) * 86400);

const COLS = "humidity, temperature, PH, N, P, K";

let sql;
if (N === 1) {
    sql = "select timestamp, " + COLS + " from NPKv1" + where + " order by timestamp;";
}
else {
    // group consecutive readings into blocks of N
    sql =
        "with r as (select timestamp, " + COLS + "," +
        " (row_number() over (order by timestamp) - 1)/" + N + " as g" +
        " from NPKv1" + where + ")" +
        " select cast(avg(timestamp) as integer) as timestamp," +
        " avg(humidity) as humidity, avg(temperature) as temperature, avg(PH) as PH," +
        " avg(N) as N, avg(P) as P, avg(K) as K, count(*) as n_raw" +
        " from r group by g order by timestamp;";
}

msg.topic = sql;

const rangeTxt = (range === "all") ? "all data" : "last " + range + " days";
node.status({ fill: "blue", shape: "dot",
              text: rangeTxt + ", avg of " + N });
return msg;
'''
by_id[RANGE_FN]["func"] = RANGE_FUNC

# ---- counter: report readings behind the points, and warn when heavy ----
COUNT_FUNC = r'''const rows = Array.isArray(msg.payload) ? msg.payload : [];
const N = flow.get("avgN") || 5;
const range = flow.get("range") || "7";
const rangeTxt = (range === "all") ? "all data" : "last " + range + " days";

if (rows.length === 0) {
    msg.payload = "no data in " + rangeTxt;
    node.status({ fill: "yellow", shape: "ring", text: "0 points" });
    return msg;
}

const fmt = function (secs) {
    return new Date(secs * 1000).toISOString().slice(0, 16).replace("T", " ");
};

// n_raw is present only when averaging; raw mode is one reading per point
let readings = 0;
for (const r of rows) { readings += (r.n_raw || 1); }

const pts = rows.length;
const total = pts * 6;

msg.payload = pts.toLocaleString() + " points/chart from " +
              readings.toLocaleString() + " readings" +
              (N > 1 ? " (avg of " + N + ")" : " (raw)") +
              " · " + fmt(rows[0].timestamp) + " to " + fmt(rows[rows.length - 1].timestamp);

if (total > 20000) {
    msg.payload += " · heavy: " + total.toLocaleString() + " points on screen";
    node.status({ fill: "red", shape: "dot", text: pts + " x6 = " + total });
} else {
    node.status({ fill: "green", shape: "dot", text: pts + " x6 = " + total });
}
return msg;
'''
by_id[COUNT_FN]["func"] = COUNT_FUNC

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("decimation mode set; flow now has %d nodes" % len(flows))
