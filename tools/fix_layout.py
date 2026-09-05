"""Tidy the controls group.

Problems fixed:
  - order 0 means "unordered" in dashboard 1, so the Time range dropdown was
    appended after everything else. Every widget now has an explicit 1..4.
  - the button and text widgets both had height 0 (auto) and overlapped;
    both get explicit heights.
  - the status line was too long for the group and got clipped mid-date.
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

GROUP = "d91c5f0cac293037"
RANGE_DD = "aa11bb22cc33dd01"
AVG_DD = "aa11bb22cc33dd05"
BUTTON = "f794c8e7bc416e61"
COUNT_TXT = "aa11bb22cc33dd04"
COUNT_FN = "aa11bb22cc33dd03"

GROUP_WIDTH = 6

grp = by_id[GROUP]
grp["name"] = "Controls"
grp["width"] = GROUP_WIDTH
grp["order"] = 1

# explicit order top to bottom, full-width rows, explicit heights
layout = [
    (RANGE_DD,   1, GROUP_WIDTH, 1),
    (AVG_DD,     2, GROUP_WIDTH, 1),
    (BUTTON,     3, GROUP_WIDTH, 1),
    (COUNT_TXT,  4, GROUP_WIDTH, 2),   # 2 rows so the text is not clipped
]
for nid, order, w, h in layout:
    n = by_id[nid]
    n["order"] = order
    n["width"] = w
    n["height"] = h

txt = by_id[COUNT_TXT]
txt["label"] = ""              # the text is self-describing; label wasted a line
txt["layout"] = "col-center"
txt["fontSize"] = 13

# charts sit in their own groups; give those an explicit order too so the
# Controls group stays at the top of the Charts tab
by_id["b3b2ba7659a6611a"]["order"] = 2   # Parameter
by_id["fece59b930caf4ae"]["order"] = 3   # NPK

# ---- shorter status line so it fits the group ----
COUNT_FUNC = r'''const rows = Array.isArray(msg.payload) ? msg.payload : [];
const N = flow.get("avgN") || 5;
const range = flow.get("range") || "7";
const rangeTxt = (range === "all") ? "all data" : "last " + range + "d";

if (rows.length === 0) {
    msg.payload = "no data in " + rangeTxt;
    node.status({ fill: "yellow", shape: "ring", text: "0 points" });
    return msg;
}

// short form: 08-15 13:20
const fmt = function (secs) {
    return new Date(secs * 1000).toISOString().slice(5, 16).replace("T", " ");
};

let readings = 0;
for (const r of rows) { readings += (r.n_raw || 1); }

const pts = rows.length;
const total = pts * 6;

msg.payload =
    pts.toLocaleString() + " pts/chart · " +
    (N > 1 ? "avg " + N : "raw") + " · " +
    readings.toLocaleString() + " readings\n" +
    fmt(rows[0].timestamp) + " → " + fmt(rows[rows.length - 1].timestamp);

if (total > 20000) {
    msg.payload += " · heavy (" + total.toLocaleString() + " on screen)";
    node.status({ fill: "red", shape: "dot", text: pts + " x6 = " + total });
} else {
    node.status({ fill: "green", shape: "dot", text: pts + " x6 = " + total });
}
return msg;
'''
by_id[COUNT_FN]["func"] = COUNT_FUNC

# render the newline in the text widget
txt["format"] = '<div style="white-space:pre-line;line-height:1.4">{{msg.payload}}</div>'

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("layout fixed")
for nid, order, w, h in layout:
    print("  %-12s order=%d %dx%d" % (by_id[nid].get("name") or by_id[nid]["type"], order, w, h))
