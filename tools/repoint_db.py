"""Publish the working flow into the project folder and point it at the
project's own DB_01.db (rather than the old D:\\Erick\\... path)."""
import json, os

SRC = os.path.join(os.environ["USERPROFILE"], ".node-red", "flows.json")
REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")
DB = os.path.join(REPO, "DB_01.db")

flows = json.load(open(SRC, encoding="utf-8"))

n = 0
for node in flows:
    if node.get("type") == "sqlitedb":
        node["db"] = DB
        n += 1

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("repointed %d sqlitedb node(s) -> %s" % (n, DB))
print("wrote", DST)
