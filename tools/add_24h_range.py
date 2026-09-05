"""Add a "Last 24 hours" option to the chart range selector.

The builder already works in days, so 24 h is range "1"; only the accepted
list and the labels need to know about it.
"""
import json, os, sys

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

RANGE_DD = "aa11bb22cc33dd01"
RANGE_FN = "aa11bb22cc33dd02"
COUNT_FN = "aa11bb22cc33dd03"

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

# ---- dropdown: 24 h first, then the existing spans ----
by_id[RANGE_DD]["options"] = [
    {"label": "Last 24 hours", "value": "1",   "type": "str"},
    {"label": "Last 7 days",   "value": "7",   "type": "str"},
    {"label": "Last 15 days",  "value": "15",  "type": "str"},
    {"label": "Last month",    "value": "30",  "type": "str"},
    {"label": "Last 3 months", "value": "90",  "type": "str"},
    {"label": "All data",      "value": "all", "type": "str"},
]

def patch(node_id, pairs):
    """Apply exact string replacements, failing loudly if one does not match."""
    fn = by_id[node_id]
    src = fn["func"]
    for old, new in pairs:
        if old not in src:
            sys.exit("PATCH FAILED in %s: %r not found" % (fn.get("name"), old[:60]))
        src = src.replace(old, new)
    fn["func"] = src

# "last 1 days" reads badly; say 24 h instead
LABEL_HELPER = '''const rangeLabel = function (r) {
    if (r === "all") { return "all data"; }
    if (r === "1")   { return "last 24 h"; }
    return "last " + r + " days";
};
'''

patch(RANGE_FN, [
    ('const RANGES = ["7", "15", "30", "90", "all"];',
     'const RANGES = ["1", "7", "15", "30", "90", "all"];'),
    ('const rangeTxt = (range === "all") ? "all data" : "last " + range + " days";',
     LABEL_HELPER + 'const rangeTxt = rangeLabel(range);'),
])

patch(COUNT_FN, [
    ('const rangeTxt = (range === "all") ? "all data" : "last " + range + "d";',
     'const rangeTxt = (range === "all") ? "all data"\n'
     '    : (range === "1") ? "last 24 h" : "last " + range + "d";'),
])

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("added 24 h option")
print("dropdown:", [o["label"] for o in by_id[RANGE_DD]["options"]])
