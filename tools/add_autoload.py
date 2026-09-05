"""Charts were empty until Refresh was pressed. Load them once at start-up so
a freshly opened dashboard shows data (ui_chart replays its stored series to
any client that connects afterwards)."""
import json, os

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
DST = os.path.join(REPO, "flows.json")

flows = json.load(open(DST, encoding="utf-8"))
by_id = {n["id"]: n for n in flows}

TAB = "55ef81d4c950013b"
RANGE_FN = "aa11bb22cc33dd02"
AUTOLOAD = "aa11bb22cc33dd06"

if AUTOLOAD not in by_id:
    flows.append({
        "id": AUTOLOAD,
        "type": "inject",
        "z": TAB,
        "name": "load charts at start",
        "props": [{"p": "payload"}],
        "repeat": "",
        "crontab": "",
        "once": True,
        "onceDelay": "3",     # let the sqlite node open the file first
        "topic": "",
        "payload": "",
        "payloadType": "str",  # empty string -> builder reuses stored selections
        "x": 480,
        "y": 500,
        "wires": [[RANGE_FN]],
    })

json.dump(flows, open(DST, "w", encoding="utf-8"), indent=4)
print("autoload added; flow now has %d nodes" % len(flows))
