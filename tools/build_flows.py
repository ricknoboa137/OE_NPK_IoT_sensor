import json, os

SRC = r"C:\Users\User\Documents\GitHub\NPK_Sensor\flows.json"
DST = os.path.join(os.environ["USERPROFILE"], ".node-red", "flows.json")

flows = json.load(open(SRC, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

# ---- 1. CREATE TABLE: add timestamp columns, idempotent, run once at start ----
create = by_id["8ca9efddfa25bc49"]
create["topic"] = ("CREATE TABLE IF NOT EXISTS NPKv1 ("
                   "timestamp INTEGER, ts_utc TEXT, "
                   "humidity REAL, temperature REAL, PH REAL, "
                   "N REAL, P REAL, K REAL);")
create["name"] = "create table"
create["once"] = True
create["onceDelay"] = 0.5

# ---- 2. Insert function: parameterised, validated ----
INSERT_FN = r'''const p = msg.payload;

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
    $ph: num(p.PH),
    $n: num(p.Nitrogen),
    $p: num(p.Phosphorus),
    $k: num(p.Potassium)
};

node.status({ fill: "green", shape: "dot", text: msg.params.$ts_utc });
return msg;
'''
fn = by_id["06fee8be07ade0d1"]
fn["name"] = "build insert params"
fn["func"] = INSERT_FN
fn["wires"] = [["a1b2c3d4e5f60001"]]     # -> new prepared insert node

# ---- 3. Dedicated prepared-mode sqlite node for the insert ----
insert_node = {
    "id": "a1b2c3d4e5f60001",
    "type": "sqlite",
    "z": "55ef81d4c950013b",
    "mydb": "e9b358432d3979d4",
    "sqlquery": "prepared",
    "sql": ("INSERT INTO NPKv1 (timestamp, ts_utc, humidity, temperature, PH, N, P, K) "
            "VALUES ($ts, $ts_utc, $humidity, $temperature, $ph, $n, $p, $k)"),
    "name": "insert reading",
    "x": 800,
    "y": 440,
    "wires": [["36a7f23d8851cb03"]],
}
flows.append(insert_node)
by_id[insert_node["id"]] = insert_node

# existing node 02673b1a... now serves only the "delete all" inject
by_id["02673b1a6fde3fd6"]["name"] = "delete rows"

# ---- 4. Charts: keep 24h, not 1h ----
CHART_COL = {
    "f5c50ae8e3103725": ("temperature", "Temperature"),
    "781414fade39dcce": ("humidity",    "Moisture"),
    "bc40c6c966966db6": ("PH",          "pH"),
    "f37fe8a41957eac6": ("N",           "Nitrogen"),
    "b0a088358ead9f5e": ("P",           "Phosphorus"),
    "ea1fc58237731cbc": ("K",           "Potassium"),
}
for cid in CHART_COL:
    by_id[cid]["removeOlder"] = 24
    by_id[cid]["removeOlderUnit"] = "3600"

# ---- 5. ToPlotData functions: right series name, right column, ms x-axis ----
PLOT_FN = '''const rows = Array.isArray(msg.payload) ? msg.payload : [];

const out = [{
    series: ["%SERIES%"],
    data: [[]],
    labels: [""]
}];

for (const item of rows) {
    if (item.%COL% === null || item.%COL% === undefined) { continue; }
    out[0].data[0].push({
        x: item.timestamp * 1000,   // stored as unix seconds, chart wants ms
        y: item.%COL%
    });
}

msg.payload = out;
return msg;
'''
# function id -> chart it feeds
PLOT_FUNCS = {
    "444577de7c3d52e3": "f5c50ae8e3103725",
    "f3a810c6c804fea7": "781414fade39dcce",
    "765ce5f385f25cf2": "bc40c6c966966db6",
    "2d0025fada26f1a6": "f37fe8a41957eac6",
    "e204e982b7dd2d0a": "b0a088358ead9f5e",
    "eb8d5f38547b608e": "ea1fc58237731cbc",
}
for fid, cid in PLOT_FUNCS.items():
    col, series = CHART_COL[cid]
    node = by_id[fid]
    node["name"] = "ToPlotData " + col
    node["func"] = PLOT_FN.replace("%SERIES%", series).replace("%COL%", col)

# ---- 6. Queries ----
by_id["f794c8e7bc416e61"]["payload"] = "select * from NPKv1 order by timestamp;"
by_id["f794c8e7bc416e61"]["topic"] = "select * from NPKv1 order by timestamp;"

by_id["7f38779fb25f8321"]["topic"] = (
    "select *, datetime(timestamp,'unixepoch') as utc from NPKv1 "
    "where timestamp between strftime('%s','now','-7 days') and strftime('%s','now') "
    "order by timestamp;")
by_id["7f38779fb25f8321"]["name"] = "last 7 days"

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("wrote", DST, len(flows), "nodes")
