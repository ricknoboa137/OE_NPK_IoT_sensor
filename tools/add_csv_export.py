"""Add a "Last 2 days" range and a CSV export of whatever is currently plotted.

Export path:
    ui_template link -> GET /npk.csv -> csv query -> sqlite -> rows to csv
                                                            -> http response

The endpoint replays the SQL the chart query last ran (stashed in flow context
by "build range query"), so the file always matches the plot, including the
averaging factor. If nothing has been plotted yet it falls back to the stored
selection, and finally to the 7-day default.

Served over HTTP rather than a browser Blob so it works from any machine
viewing the dashboard and does not depend on Angular in ui_template.
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

TAB = "55ef81d4c950013b"
SQLITE_DB = "e9b358432d3979d4"
RANGE_DD = "aa11bb22cc33dd01"
RANGE_FN = "aa11bb22cc33dd02"
GRP_CONTROLS = "d91c5f0cac293037"

HTTP_IN = "cc55dd66ee770001"
FN_CSVQ = "cc55dd66ee770002"
SQL_CSV = "cc55dd66ee770003"
FN_CSV = "cc55dd66ee770004"
HTTP_OUT = "cc55dd66ee770005"
UI_LINK = "cc55dd66ee770006"

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}


def put(node):
    if node["id"] in by_id:
        by_id[node["id"]].update(node)
    else:
        flows.append(node)
        by_id[node["id"]] = node


# ---------------------------------------------------------------- 2 days
by_id[RANGE_DD]["options"] = [
    {"label": "Last 24 hours", "value": "1",   "type": "str"},
    {"label": "Last 2 days",   "value": "2",   "type": "str"},
    {"label": "Last 7 days",   "value": "7",   "type": "str"},
    {"label": "Last 15 days",  "value": "15",  "type": "str"},
    {"label": "Last month",    "value": "30",  "type": "str"},
    {"label": "Last 3 months", "value": "90",  "type": "str"},
    {"label": "All data",      "value": "all", "type": "str"},
]

fn = by_id[RANGE_FN]
src = fn["func"]

old_ranges = 'const RANGES = ["1", "7", "15", "30", "90", "all"];'
new_ranges = 'const RANGES = ["1", "2", "7", "15", "30", "90", "all"];'
if old_ranges not in src:
    raise SystemExit("PATCH FAILED: RANGES list not found")
src = src.replace(old_ranges, new_ranges, 1)

# stash the query so the CSV endpoint can replay exactly what was plotted
old_tail = 'node.status({ fill: "blue", shape: "dot",\n              text: rangeTxt + ", avg of " + N });'
new_tail = ('flow.set("lastSql", sql);\n'
            'flow.set("lastDesc", rangeTxt + ", avg of " + N);\n\n'
            'node.status({ fill: "blue", shape: "dot",\n'
            '              text: rangeTxt + ", avg of " + N });')
if old_tail not in src:
    raise SystemExit("PATCH FAILED: status line not found in build range query")
src = src.replace(old_tail, new_tail, 1)
fn["func"] = src

# ---------------------------------------------------------------- endpoint
put({
    "id": HTTP_IN, "type": "http in", "z": TAB, "name": "GET /npk.csv",
    "url": "/npk.csv", "method": "get", "upload": False, "swaggerDoc": "",
    "x": 460, "y": 1700, "wires": [[FN_CSVQ]],
})

CSVQ_FUNC = r'''// Replay the query the charts last ran, so the CSV matches the plot exactly
// (same range, same averaging). Falls back to the stored selection, then to
// the 7-day default, so the endpoint works even on a fresh restart.

let sql = flow.get("lastSql");
let desc = flow.get("lastDesc");

if (!sql) {
    const range = flow.get("range") || "7";
    const N = flow.get("avgN") || 5;
    const where = (range === "all") ? ""
        : " where timestamp >= strftime('%s','now') - " + (parseInt(range, 10) * 86400);
    const COLS = "humidity, temperature, conductivity, PH, N, P, K";
    if (N === 1) {
        sql = "select timestamp, " + COLS + " from NPKv1" + where + " order by timestamp;";
    } else {
        sql = "with r as (select timestamp, " + COLS + "," +
              " (row_number() over (order by timestamp) - 1)/" + N + " as g" +
              " from NPKv1" + where + ")" +
              " select cast(avg(timestamp) as integer) as timestamp," +
              " avg(humidity) as humidity, avg(temperature) as temperature," +
              " avg(conductivity) as conductivity, avg(PH) as PH," +
              " avg(N) as N, avg(P) as P, avg(K) as K, count(*) as n_raw" +
              " from r group by g order by timestamp;";
    }
    desc = (range === "all") ? "all data" : "last " + range + " days, avg of " + N;
}

msg.topic = sql;
msg.desc = desc;
node.status({ fill: "blue", shape: "dot", text: desc || "default" });
return msg;
'''
put({
    "id": FN_CSVQ, "type": "function", "z": TAB, "name": "csv query",
    "func": CSVQ_FUNC, "outputs": 1, "timeout": 0, "noerr": 0,
    "initialize": "", "finalize": "", "libs": [],
    "x": 660, "y": 1700, "wires": [[SQL_CSV]],
})

put({
    "id": SQL_CSV, "type": "sqlite", "z": TAB, "mydb": SQLITE_DB,
    "sqlquery": "msg.topic", "sql": "", "name": "read for csv",
    "x": 860, "y": 1700, "wires": [[FN_CSV]],
})

CSV_FUNC = r'''// Turn the query result into a CSV download.
//
// timestamp is stored as unix seconds; the file carries both the epoch value
// and a readable UTC column so it opens sensibly in a spreadsheet without
// anyone having to convert anything.

const rows = Array.isArray(msg.payload) ? msg.payload : [];

const COLS = ["timestamp", "utc", "humidity", "temperature", "conductivity",
              "PH", "N", "P", "K", "n_raw"];

const esc = function (v) {
    if (v === null || v === undefined) { return ""; }
    const s = String(v);
    // quote anything that would confuse a CSV parser
    return (s.indexOf(",") !== -1 || s.indexOf('"') !== -1 || s.indexOf("\n") !== -1)
        ? '"' + s.replace(/"/g, '""') + '"'
        : s;
};

const NL = String.fromCharCode(13) + String.fromCharCode(10);   // CRLF for Excel
const out = [COLS.join(",")];

for (const r of rows) {
    const utc = (r.timestamp === null || r.timestamp === undefined)
        ? "" : new Date(r.timestamp * 1000).toISOString().slice(0, 19).replace("T", " ");
    out.push(COLS.map(function (c) {
        if (c === "utc") { return esc(utc); }
        return esc(r[c]);
    }).join(","));
}

const stamp = new Date().toISOString().slice(0, 16).replace("T", "_").replace(":", "");
const slug = String(msg.desc || "export").replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "");
const filename = "npk_" + slug + "_" + stamp + ".csv";

msg.payload = out.join(NL) + NL;
msg.headers = {
    "Content-Type": "text/csv; charset=utf-8",
    "Content-Disposition": 'attachment; filename="' + filename + '"',
};
msg.statusCode = 200;

node.status({ fill: "green", shape: "dot", text: rows.length + " rows" });
return msg;
'''
put({
    "id": FN_CSV, "type": "function", "z": TAB, "name": "rows to csv",
    "func": CSV_FUNC, "outputs": 1, "timeout": 0, "noerr": 0,
    "initialize": "", "finalize": "", "libs": [],
    "x": 1060, "y": 1700, "wires": [[HTTP_OUT]],
})

put({
    "id": HTTP_OUT, "type": "http response", "z": TAB, "name": "",
    "statusCode": "", "headers": {},
    "x": 1250, "y": 1700, "wires": [],
})

# ---------------------------------------------------------------- button
put({
    "id": UI_LINK, "type": "ui_template", "z": TAB, "group": GRP_CONTROLS,
    "name": "download csv", "order": 5, "width": 6, "height": 1,
    "format": (
        '<a href="/npk.csv" target="_blank" rel="noopener"\n'
        '   style="display:block;box-sizing:border-box;width:100%;padding:9px 0;\n'
        '          text-align:center;background:#0288d1;color:#fff;font-weight:500;\n'
        '          text-decoration:none;border-radius:2px;font-size:14px;\n'
        '          letter-spacing:.5px">DOWNLOAD CSV</a>'
    ),
    "storeOutMessages": True, "fwdInMessages": True, "resendOnRefresh": True,
    "templateScope": "local", "className": "",
    "x": 1060, "y": 1660, "wires": [[]],
})

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("added 2-day range and CSV export; nodes: %d" % len(flows))
