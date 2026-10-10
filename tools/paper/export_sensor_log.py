"""Freeze the Node-RED log as the versioned file the manuscript is computed from.

Run once, or again only if the manuscript is to be recomputed on a longer
record. Reads the live database kept beside the firmware (which is not under
version control, because it keeps growing) and writes data/sensor_log.csv.gz
in the paper repository. Values are written with repr(), so they read back
bit for bit.

    C:/Users/User/anaconda3/python.exe tools/paper/export_sensor_log.py
"""
import csv, gzip, sqlite3, pathlib
import paper_data as pd_

DB = pathlib.Path(__file__).resolve().parent.parent.parent / "DB_01.db"
COLUMNS = ("timestamp", "ts_utc", "humidity", "temperature", "PH", "N", "P", "K", "conductivity", "ok")

con = sqlite3.connect(DB)
rows = con.execute(f"select {', '.join(COLUMNS)} from NPKv1 order by timestamp, rowid").fetchall()
pd_.SENSOR_LOG.parent.mkdir(exist_ok=True)
# mtime=0 keeps the compressed file identical when the content is unchanged
with open(pd_.SENSOR_LOG, "wb") as raw:
    with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        import io
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        w = csv.writer(text, lineterminator="\n")
        w.writerow(COLUMNS)
        for r in rows:
            w.writerow(["" if v is None else (v if isinstance(v, str) else repr(v)) for v in r])
        text.flush()
print(f"{len(rows)} readings written to {pd_.SENSOR_LOG}  ({pd_.SENSOR_LOG.stat().st_size/1e6:.2f} MB)")
print(f"first {rows[0][1]} UTC, last {rows[-1][1]} UTC")
