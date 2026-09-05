"""Add a time-range selector (7 / 15 / 30 / 90 days) to the dashboard.

    dropdown ---\
                 +--> build range query --> sqlite --> 6x ToPlotData --> charts
    Refresh   ---/

The query buckets rows with AVG() so a 3-month range is ~1500 points per chart
instead of ~1.5 million.
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

TAB = "55ef81d4c950013b"
SQLITE_QUERY_NODE = "6c521fc6f2276524"   # feeds all six ToPlotData functions
BUTTON = "f794c8e7bc416e61"
BUTTONS_GROUP = "d91c5f0cac293037"

DROPDOWN = "aa11bb22cc33dd01"
RANGE_FN = "aa11bb22cc33dd02"

# ---- dropdown ----
flows.append({
    "id": DROPDOWN,
    "type": "ui_dropdown",
    "z": TAB,
    "name": "range",
    "label": "Time range",
    "tooltip": "How much history to plot",
    "place": "Select range",
    "group": BUTTONS_GROUP,
    "order": 0,
    "width": 0,
    "height": 0,
    "passthru": True,
    "multiple": False,
    "options": [
        {"label": "Last 7 days",  "value": "7",  "type": "str"},
        {"label": "Last 15 days", "value": "15", "type": "str"},
        {"label": "Last month",   "value": "30", "type": "str"},
        {"label": "Last 3 months","value": "90", "type": "str"},
    ],
    "payload": "",
    "topic": "range",
    "topicType": "str",
    "className": "",
    "x": 480,
    "y": 580,
    "wires": [[RANGE_FN]],
})

# ---- query builder ----
RANGE_FUNC = r'''// Build a bucketed query for the selected range.
// Ranges are anchored to the newest reading in the database, not to the clock,
// so archived data still plots when no sensor is currently publishing.

const ALLOWED = [7, 15, 30, 90];
const TARGET_POINTS = 1500;   // per chart, keeps the browser responsive

let days = parseInt(msg.payload, 10);
if (isNaN(days) || ALLOWED.indexOf(days) === -1) {
    days = flow.get("rangeDays") || 7;      // Refresh button reuses last choice
}
flow.set("rangeDays", days);

const span = days * 86400;
const bucket = Math.max(1, Math.round(span / TARGET_POINTS));

msg.topic =
    "select cast(timestamp/" + bucket + " as integer)*" + bucket + " as timestamp," +
    " avg(humidity) as humidity, avg(temperature) as temperature, avg(PH) as PH," +
    " avg(N) as N, avg(P) as P, avg(K) as K" +
    " from NPKv1" +
    " where timestamp >= (select max(timestamp) from NPKv1) - " + span +
    " group by timestamp/" + bucket +
    " order by timestamp;";

node.status({ fill: "blue", shape: "dot", text: days + " days / " + bucket + "s buckets" });
return msg;
'''

flows.append({
    "id": RANGE_FN,
    "type": "function",
    "z": TAB,
    "name": "build range query",
    "func": RANGE_FUNC,
    "outputs": 1,
    "timeout": 0,
    "noerr": 0,
    "initialize": "",
    "finalize": "",
    "libs": [],
    "x": 660,
    "y": 580,
    "wires": [[SQLITE_QUERY_NODE]],
})

# ---- rewire the Refresh button through the same builder ----
btn = by_id[BUTTON]
btn["label"] = "Refresh"
btn["payload"] = ""
btn["payloadType"] = "str"
btn["topic"] = "refresh"
btn["topicType"] = "str"
btn["order"] = 2
btn["wires"] = [[RANGE_FN]]
btn["x"] = 480
btn["y"] = 620

# ---- charts: auto x-axis labels, retention wide enough for 90 days ----
CHARTS = ["f5c50ae8e3103725", "781414fade39dcce", "bc40c6c966966db6",
          "f37fe8a41957eac6", "b0a088358ead9f5e", "ea1fc58237731cbc"]
for cid in CHARTS:
    by_id[cid]["xformat"] = "auto"
    by_id[cid]["removeOlder"] = 730
    by_id[cid]["removeOlderUnit"] = "86400"

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("added range selector; flow now has %d nodes" % len(flows))
