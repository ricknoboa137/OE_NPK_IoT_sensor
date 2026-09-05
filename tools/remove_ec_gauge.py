"""Remove the conductivity gauge from the Lectures tab, matching the chart removal."""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")
EC_GAUGE = "ca11b0a000000001"

flows = json.load(open(DST, encoding="utf-8"))
before = len(flows)

flows = [n for n in flows if n["id"] != EC_GAUGE]
for n in flows:
    for port in n.get("wires", []) or []:
        while EC_GAUGE in port:
            port.remove(EC_GAUGE)
            print("unwired from %s (%s)" % (n["id"], n.get("name") or n["type"]))

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("removed %d node; flow now has %d" % (before - len(flows), len(flows)))
print("still referenced:", EC_GAUGE in json.dumps(flows))
