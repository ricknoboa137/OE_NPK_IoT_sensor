"""Snapshot the probe's own correction factors, and restore them later.

    [Backup probe registers] -> "sensor" -> NPKreply -> parse -> SQLite
    [Restore factory backup] -> read the OLDEST snapshot -> write commands
    [List backups]           -> read the table -> console log

Snapshots live in probe_cal_backup inside the same DB_01.db the readings use,
so they survive a Node-RED restart (flow context does not).

What can be written back, per NpkConsole::cmdSensor:
    sensor factor <n|p|k> <float>          yes
    sensor offset <temp|hum|ec|ph> <int>   yes
    N/P/K offset registers                 no write command exists
    0x0022-0x0024 (EC/salinity/TDS)        no write command exists
The last two are captured anyway, so the values are on record even though a
restore cannot push them back.
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

TAB = "55ef81d4c950013b"
GRP_CAL = "ca11b0a000000011"
SQLITE_DB = "e9b358432d3979d4"
CAL_OUT = "ca11b0a000000023"      # mqtt out -> NPKcommand
CAL_LOG_FN = "ca11b0a000000025"   # console log
REPLY_IN = "ca11b0a000000024"     # mqtt in <- NPKreply

BTN_BACKUP = "ca11b0a000000040"
BTN_RESTORE = "ca11b0a000000041"
BTN_LIST = "ca11b0a000000042"
FN_CONTROL = "ca11b0a000000043"
FN_PARSE = "ca11b0a000000044"
SQL_INSERT = "ca11b0a000000045"
SQL_QUERY = "ca11b0a000000046"
FN_RESULT = "ca11b0a000000047"
DELAY_NODE = "ca11b0a000000048"
INJ_CREATE = "ca11b0a000000049"
SQL_CREATE = "ca11b0a00000004a"

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}


def put(node):
    """Add a node, or update it in place if the id already exists."""
    if node["id"] in by_id:
        by_id[node["id"]].update(node)
    else:
        flows.append(node)
        by_id[node["id"]] = node


# ---------------------------------------------------------------- buttons
for bid, label, payload, order, bg in [
    (BTN_BACKUP,  "Backup probe registers", "act:backup",  11, "#2e7d32"),
    (BTN_RESTORE, "Restore factory backup", "act:restore", 12, "#ef6c00"),
    (BTN_LIST,    "List backups",           "act:backups", 13, ""),
]:
    put({
        "id": bid, "type": "ui_button", "z": TAB, "group": GRP_CAL,
        "name": label, "label": label, "order": order, "width": 6, "height": 1,
        "passthru": False, "tooltip": "", "color": "", "bgcolor": bg,
        "className": "", "icon": "", "payload": payload, "payloadType": "str",
        "topic": "action", "topicType": "str",
        "x": 460, "y": 1500 + order * 20, "wires": [[FN_CONTROL]],
    })

# ---------------------------------------------------------------- control
CONTROL_FUNC = '''// Backup / restore controller.
//
//   act:backup   ask the node for its register dump and arm the parser
//   act:restore  read the OLDEST snapshot and replay it onto the probe
//   act:backups  list what has been captured
//
// outputs: [ MQTT command, SQLite query, console log ]

const s = String(msg.payload === undefined ? "" : msg.payload);

if (s === "act:backup") {
    // the parser only stores a dump that was asked for here, so pressing
    // "Read probe registers" on its own never creates a snapshot
    flow.set("pendingBackup", Date.now());
    node.status({ fill: "blue", shape: "dot", text: "awaiting dump" });
    return [
        { topic: "NPKcommand", payload: "sensor" },
        null,
        { payload: { line: "> sensor  (capturing a backup)", kind: "sent" } }
    ];
}

if (s === "act:restore") {
    // oldest first: the earliest snapshot is the closest thing to factory
    flow.set("restoreMode", "apply");
    return [null,
        { topic: "select * from probe_cal_backup order by ts limit 1;" },
        { payload: { line: "> reading the oldest backup", kind: "sent" } }];
}

if (s === "act:backups") {
    flow.set("restoreMode", "list");
    return [null,
        { topic: "select ts, ts_utc, note from probe_cal_backup order by ts;" },
        { payload: { line: "> listing backups", kind: "sent" } }];
}

return null;
'''
put({
    "id": FN_CONTROL, "type": "function", "z": TAB, "name": "backup control",
    "func": CONTROL_FUNC, "outputs": 3, "timeout": 0, "noerr": 0,
    "initialize": "", "finalize": "", "libs": [],
    "x": 700, "y": 1560, "wires": [[CAL_OUT], [SQL_QUERY], [CAL_LOG_FN]],
})

# ---------------------------------------------------------------- parser
PARSE_FUNC = '''// Parse the "sensor" register dump into a snapshot row.
//
// Runs only when a backup was requested (flow.pendingBackup), so a manual
// "Read probe registers" press does not silently create snapshots.
//
// Lines look like:
//   0x0050  temperature offset   raw      0  -> 0.00
//   0x04E8  n factor 0.00000   offset 0
//   0x0022  conductivity factor       0   factory default 0
// Classified by register number rather than by wording, which is sturdier.

const NL = String.fromCharCode(10);
const text = String(msg.payload);

if (text.indexOf("Sensor-side calibration") === -1) { return null; }   // not a dump

const asked = flow.get("pendingBackup");
if (!asked) { return null; }
flow.set("pendingBackup", null);

const OFFSETS = { "0X0050": "temp", "0X0051": "hum", "0X0052": "ec", "0X0053": "ph" };
const NUTRIENTS = { "0X04E8": "n", "0X04F2": "p", "0X04FC": "k" };
const READONLY = { "0X0022": "ec_factor", "0X0023": "salinity_factor", "0X0024": "tds_factor" };

const snap = { offsets: {}, factors: {}, nutrient_offsets: {}, readonly: {}, unread: [] };

const lines = text.split(NL);
for (const raw of lines) {
    const t = raw.trim().split(/ +/);
    if (!t.length || t[0].substring(0, 2).toUpperCase() !== "0X") { continue; }
    const reg = t[0].toUpperCase();

    if (raw.indexOf("no reply") !== -1) { snap.unread.push(reg); continue; }

    if (OFFSETS[reg] !== undefined) {
        const i = t.indexOf("raw");
        const v = Number(t[i + 1]);
        if (i !== -1 && !isNaN(v)) { snap.offsets[OFFSETS[reg]] = v; }
    } else if (NUTRIENTS[reg] !== undefined) {
        const key = NUTRIENTS[reg];
        const fi = t.indexOf("factor");
        const oi = t.indexOf("offset");
        const f = Number(t[fi + 1]);
        const o = Number(t[oi + 1]);
        if (fi !== -1 && !isNaN(f)) { snap.factors[key] = f; }
        if (oi !== -1 && !isNaN(o)) { snap.nutrient_offsets[key] = o; }
    } else if (READONLY[reg] !== undefined) {
        const v = Number(t[t.indexOf("factor") + 1]);
        if (!isNaN(v)) { snap.readonly[READONLY[reg]] = v; }
    }
}

const nFactors = Object.keys(snap.factors).length;
const nOffsets = Object.keys(snap.offsets).length;
if (nFactors === 0 && nOffsets === 0) {
    return [null, { payload: { line: "backup aborted: nothing parsed from the dump",
                               kind: "error" } }];
}

const now = new Date();
const note = nFactors + " factors, " + nOffsets + " offsets" +
             (snap.unread.length ? ", " + snap.unread.length + " unread" : "");

msg.params = {
    $ts: Math.floor(now.getTime() / 1000),
    $ts_utc: now.toISOString().slice(0, 19).replace("T", " "),
    $note: note,
    $data: JSON.stringify(snap)
};

node.status({ fill: "green", shape: "dot", text: "saved: " + note });

return [msg, { payload: { line: "backup saved (" + note + "): " +
                                 JSON.stringify(snap.factors) + " " +
                                 JSON.stringify(snap.offsets), kind: "sent" } }];
'''
put({
    "id": FN_PARSE, "type": "function", "z": TAB, "name": "parse sensor dump",
    "func": PARSE_FUNC, "outputs": 2, "timeout": 0, "noerr": 0,
    "initialize": "", "finalize": "", "libs": [],
    "x": 700, "y": 1460, "wires": [[SQL_INSERT], [CAL_LOG_FN]],
})

# NPKreply feeds the parser as well as the log
if FN_PARSE not in by_id[REPLY_IN]["wires"][0]:
    by_id[REPLY_IN]["wires"][0].append(FN_PARSE)

# ---------------------------------------------------------------- storage
put({
    "id": SQL_INSERT, "type": "sqlite", "z": TAB, "mydb": SQLITE_DB,
    "sqlquery": "prepared",
    "sql": "INSERT INTO probe_cal_backup (ts, ts_utc, note, data) "
           "VALUES ($ts, $ts_utc, $note, $data)",
    "name": "store backup", "x": 950, "y": 1460, "wires": [[]],
})

put({
    "id": INJ_CREATE, "type": "inject", "z": TAB, "name": "create backup table",
    "props": [{"p": "payload"}, {"p": "topic", "vt": "str"}],
    "repeat": "", "crontab": "", "once": True, "onceDelay": "4",
    "topic": "CREATE TABLE IF NOT EXISTS probe_cal_backup ("
             "ts INTEGER, ts_utc TEXT, note TEXT, data TEXT);",
    "payload": "", "payloadType": "date",
    "x": 460, "y": 1420, "wires": [[SQL_CREATE]],
})
put({
    "id": SQL_CREATE, "type": "sqlite", "z": TAB, "mydb": SQLITE_DB,
    "sqlquery": "msg.topic", "sql": "", "name": "backup table",
    "x": 700, "y": 1420, "wires": [[]],
})

put({
    "id": SQL_QUERY, "type": "sqlite", "z": TAB, "mydb": SQLITE_DB,
    "sqlquery": "msg.topic", "sql": "", "name": "read backups",
    "x": 950, "y": 1560, "wires": [[FN_RESULT]],
})

# ---------------------------------------------------------------- restore
RESULT_FUNC = '''// Turn a stored snapshot back into write commands, or list what exists.
// outputs: [ commands (rate limited), console log ]

const NL = String.fromCharCode(10);
const rows = Array.isArray(msg.payload) ? msg.payload : [];
const mode = flow.get("restoreMode") || "list";

if (rows.length === 0) {
    return [null, { payload: { line: "no backups stored yet - press Backup probe registers first",
                               kind: "error" } }];
}

if (mode === "list") {
    const lines = rows.map(function (r) { return "  " + r.ts_utc + "   " + r.note; });
    return [null, { payload: { line: "backups on record:" + NL + lines.join(NL),
                               kind: "reply" } }];
}

let snap;
try { snap = JSON.parse(rows[0].data); }
catch (e) {
    return [null, { payload: { line: "backup is unreadable: " + e.message, kind: "error" } }];
}

const cmds = [];
const warn = [];

// gains: sensor factor <n|p|k> <float>
for (const key of ["n", "p", "k"]) {
    const v = snap.factors ? snap.factors[key] : undefined;
    if (v === undefined || v === null || isNaN(v)) { continue; }
    cmds.push("sensor factor " + key + " " + v);
    if (v === 0) {
        warn.push("note: " + key + " gain in this backup is 0, which is what the probe " +
                  "shipped with - a two-point solve cannot run until it is set to 1.0");
    }
}

// offsets: sensor offset <temp|hum|ec|ph> <int>
for (const key of ["temp", "hum", "ec", "ph"]) {
    const v = snap.offsets ? snap.offsets[key] : undefined;
    if (v === undefined || v === null || isNaN(v)) { continue; }
    cmds.push("sensor offset " + key + " " + Math.round(v));
}

if (cmds.length === 0) {
    return [null, { payload: { line: "backup holds nothing writable", kind: "error" } }];
}

// no write command exists for these, so say so rather than pretending
const skipped = [];
if (snap.nutrient_offsets && Object.keys(snap.nutrient_offsets).length) {
    skipped.push("N/P/K offset registers");
}
if (snap.readonly && Object.keys(snap.readonly).length) {
    skipped.push("0x0022-0x0024 (EC/salinity/TDS factors)");
}

let summary = "restoring " + rows[0].ts_utc + ":" + NL + "  " + cmds.join(NL + "  ");
if (skipped.length) {
    summary += NL + "not restorable (no write command in the firmware): " + skipped.join(", ");
}
if (warn.length) { summary += NL + warn.join(NL); }

node.status({ fill: "blue", shape: "dot", text: cmds.length + " commands" });

// one message per command; the delay node paces them so each Modbus write
// finishes before the next arrives
const out = cmds.map(function (c) { return { topic: "NPKcommand", payload: c }; });
return [out, { payload: { line: summary, kind: "sent" } }];
'''
put({
    "id": FN_RESULT, "type": "function", "z": TAB, "name": "restore or list",
    "func": RESULT_FUNC, "outputs": 2, "timeout": 0, "noerr": 0,
    "initialize": "", "finalize": "", "libs": [],
    "x": 700, "y": 1620, "wires": [[DELAY_NODE], [CAL_LOG_FN]],
})

# pace the writes: one every 1.5 s, queue the rest
put({
    "id": DELAY_NODE, "type": "delay", "z": TAB, "name": "pace writes",
    "pauseType": "rate", "timeout": "5", "timeoutUnits": "seconds",
    "rate": "1", "nbRateUnits": "1500", "rateUnits": "millisecond",
    "randomFirst": "1", "randomLast": "5", "randomUnits": "seconds",
    "drop": False, "allowrate": False, "outputs": 1,
    "x": 950, "y": 1620, "wires": [[CAL_OUT]],
})

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("backup/restore added; nodes: %d" % len(flows))
