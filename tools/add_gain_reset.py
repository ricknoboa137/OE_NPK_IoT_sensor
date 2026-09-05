"""Add a "Set probe gain to 1.0" button.

The probe's N/P/K gain registers currently read 0.00000, and cmdSensor refuses
to compose a two-point solve on a zero gain - it tells you to run
"sensor factor <n|p|k> 1.0" first. Without this the new method cannot be
started from the dashboard at all.
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

TAB = "55ef81d4c950013b"
GRP_CAL = "ca11b0a000000011"
CAL_FN = "ca11b0a000000022"
BTN_GAIN1 = "ca11b0a000000031"

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

if BTN_GAIN1 not in by_id:
    flows.append({
        "id": BTN_GAIN1, "type": "ui_button", "z": TAB, "group": GRP_CAL,
        "name": "Set probe gain to 1.0", "label": "Set probe gain to 1.0",
        "order": 5, "width": 6, "height": 1, "passthru": False,
        "tooltip": "Required once before a two-point solve if the gain reads 0",
        "color": "", "bgcolor": "#ef6c00", "className": "", "icon": "",
        "payload": "act:gain1", "payloadType": "str",
        "topic": "action", "topicType": "str",
        "x": 460, "y": 1220, "wires": [[CAL_FN]],
    })

# push the later buttons down one slot
REORDER = {
    "ca11b0a00000002b": 3,   # LOW
    "ca11b0a00000002c": 4,   # HIGH
    BTN_GAIN1:          5,   # set gain 1.0
    "ca11b0a00000002a": 6,   # one-point trim
    "ca11b0a000000030": 7,   # read probe registers
    "ca11b0a00000002d": 8,   # read firmware A/B
    "ca11b0a00000002e": 9,   # reset channel
    "ca11b0a00000002f": 10,  # reset all
}
for nid, order in REORDER.items():
    by_id[nid]["order"] = order if nid != BTN_GAIN1 else 5

# teach the builder the new action
fn = by_id[CAL_FN]
old = '''} else if (act === "sensor") {'''
new = '''} else if (act === "gain1") {
    if (!onProbe) { return fail(ch + " has no gain register in the probe"); }
    // cmdSensor refuses to solve on a zero or NaN gain; this is the reset it
    // tells you to run first
    line = "sensor factor " + ch + " 1.0";
    note = "starting point for a probe-side solve, writes to the probe";
} else if (act === "sensor") {'''
if old not in fn["func"]:
    raise SystemExit("PATCH FAILED: anchor not found in build cal command")
fn["func"] = fn["func"].replace(old, new, 1)

# gain1 needs a channel but no reference
fn["func"] = fn["func"].replace(
    'const needsChannel = (act !== "resetall" && act !== "sensor" && act !== "list");',
    'const needsChannel = (act !== "resetall" && act !== "sensor" && act !== "list");')

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("added gain-reset button; nodes: %d" % len(flows))
