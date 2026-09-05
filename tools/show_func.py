"""Print a function node's code, to confirm an edit landed.
    python tools/show_func.py "build range query"
"""
import json, os, sys

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
flows = json.load(open(os.path.join(REPO, "flows.json"), encoding="utf-8"))
want = sys.argv[1] if len(sys.argv) > 1 else "build range query"

for n in flows:
    if n.get("type") == "function" and n.get("name") == want:
        print("=== %s (%s) ===" % (n["name"], n["id"]))
        print(n["func"])
        break
else:
    print("no function named %r" % want)
