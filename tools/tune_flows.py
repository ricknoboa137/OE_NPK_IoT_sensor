import json, os

DST = os.path.join(os.environ["USERPROFILE"], ".node-red", "flows.json")
flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

CHARTS = ["f5c50ae8e3103725", "781414fade39dcce", "bc40c6c966966db6",
          "f37fe8a41957eac6", "b0a088358ead9f5e", "ea1fc58237731cbc"]

# 24h retention would discard January data the moment it arrives at the chart.
# 730 days keeps history browsable.
for cid in CHARTS:
    by_id[cid]["removeOlder"] = 730
    by_id[cid]["removeOlderUnit"] = "86400"

# 74k points x 6 charts will choke the browser. Take the most recent 2000
# readings, re-sorted ascending for the x-axis.
q = ("select * from (select * from NPKv1 order by timestamp desc limit 2000) "
     "order by timestamp;")
btn = by_id["f794c8e7bc416e61"]
btn["payload"] = q
btn["topic"] = q
btn["label"] = "Refresh (last 2000)"

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("tuned", DST)
