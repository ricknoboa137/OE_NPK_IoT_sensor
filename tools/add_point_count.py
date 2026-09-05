"""Show how many datapoints the charts are currently displaying.

    sqlite (range query) --> point count --> ui_text ("Showing")

Reads the same result set the ToPlotData functions consume, so the number is
what is actually plotted, not what the query could have returned.
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

TAB = "55ef81d4c950013b"
SQLITE_QUERY_NODE = "6c521fc6f2276524"
BUTTONS_GROUP = "d91c5f0cac293037"

COUNT_FN = "aa11bb22cc33dd03"
COUNT_TXT = "aa11bb22cc33dd04"

COUNT_FUNC = r'''// Summarise what the charts are about to show.
const rows = Array.isArray(msg.payload) ? msg.payload : [];
const days = flow.get("rangeDays") || 7;

if (rows.length === 0) {
    msg.payload = "no data in the last " + days + " days";
    node.status({ fill: "yellow", shape: "ring", text: "0 points" });
    return msg;
}

const fmt = function (secs) {
    return new Date(secs * 1000).toISOString().slice(0, 10);
};

const first = rows[0].timestamp;
const last = rows[rows.length - 1].timestamp;

// each row becomes one point on every chart
const perChart = rows.length;
const bucketSecs = rows.length > 1 ? Math.round((last - first) / (rows.length - 1)) : 0;
const bucketTxt = bucketSecs >= 3600
    ? (bucketSecs / 3600).toFixed(1) + " h"
    : Math.round(bucketSecs / 60) + " min";

msg.payload = perChart + " points/chart (" + (perChart * 6) + " total)" +
              " · " + bucketTxt + " avg" +
              " · " + fmt(first) + " to " + fmt(last);

node.status({ fill: "green", shape: "dot", text: perChart + " points x6" });
return msg;
'''

flows.append({
    "id": COUNT_FN,
    "type": "function",
    "z": TAB,
    "name": "point count",
    "func": COUNT_FUNC,
    "outputs": 1,
    "timeout": 0,
    "noerr": 0,
    "initialize": "",
    "finalize": "",
    "libs": [],
    "x": 870,
    "y": 560,
    "wires": [[COUNT_TXT]],
})

flows.append({
    "id": COUNT_TXT,
    "type": "ui_text",
    "z": TAB,
    "group": BUTTONS_GROUP,
    "order": 3,
    "width": 0,
    "height": 0,
    "name": "showing",
    "label": "Showing",
    "format": "{{msg.payload}}",
    "layout": "col-center",
    "className": "",
    "style": False,
    "font": "",
    "fontSize": 14,
    "color": "#000000",
    "x": 1050,
    "y": 560,
    "wires": [],
})

# tap the same query result the charts use
sq = by_id[SQLITE_QUERY_NODE]
if COUNT_FN not in sq["wires"][0]:
    sq["wires"][0].append(COUNT_FN)

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("added point counter; flow now has %d nodes" % len(flows))
