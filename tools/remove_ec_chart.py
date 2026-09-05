"""Remove the conductivity chart.

The probe on this node reports no conductivity (the running firmware has six
channels and the value would read 0 regardless), so the chart is dead space.

Removed: the ui_chart, its ToPlotData function, and the wire feeding it.
Left alone: the gauge, the DB column, and the SELECT - all harmless, and the
column keeps whatever a future seven-channel build writes.
"""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

EC_CHART = "ca11b0a000000002"
EC_PLOT = "ca11b0a000000003"
QUERY_NODE = "6c521fc6f2276524"

flows = json.load(open(DST, encoding="utf-8"))
before = len(flows)

# drop the two nodes
flows = [n for n in flows if n["id"] not in (EC_CHART, EC_PLOT)]

# and any wire pointing at them
for n in flows:
    for port in n.get("wires", []) or []:
        for dead in (EC_CHART, EC_PLOT):
            while dead in port:
                port.remove(dead)
                print("unwired %s from %s (%s)" % (dead, n["id"], n.get("name") or n["type"]))

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("removed %d nodes; flow now has %d" % (before - len(flows), len(flows)))

# confirm nothing still references them
blob = json.dumps(flows)
for dead in (EC_CHART, EC_PLOT):
    print("%s still referenced: %s" % (dead, dead in blob))
