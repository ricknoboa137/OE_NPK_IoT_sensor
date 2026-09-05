"""Summarise the current flow: node types, dashboard tabs/groups, MQTT and DB config."""
import json, os
from collections import Counter

REPO = r"C:\Users\User\Documents\GitHub\NPK_Sensor"
flows = json.load(open(os.path.join(REPO, "flows.json"), encoding="utf-8"))

print("nodes:", len(flows))
print(dict(Counter(n.get("type") for n in flows)))
print()
for t in ("tab", "ui_tab"):
    for n in flows:
        if n.get("type") == t:
            print(t, n["id"], repr(n.get("label") or n.get("name")), "order", n.get("order"))
print()
for n in flows:
    if n.get("type") == "ui_group":
        print("group", n["id"], repr(n.get("name")), "tab", n.get("tab"),
              "w", n.get("width"), "order", n.get("order"))
print()
for n in flows:
    if n.get("type") in ("mqtt in", "mqtt out", "mqtt-broker", "sqlitedb"):
        print(n["type"], n["id"], repr(n.get("topic") or n.get("broker") or n.get("db")),
              "port" , n.get("port", ""))
print()
print("function/inject/ui node names:")
for n in flows:
    if n.get("type") in ("function", "inject", "ui_dropdown", "ui_button", "ui_text",
                          "ui_text_input", "ui_template", "ui_chart", "ui_gauge", "sqlite"):
        print("  %-14s %-18s %s" % (n["type"], n["id"], repr(n.get("name") or n.get("label"))))
