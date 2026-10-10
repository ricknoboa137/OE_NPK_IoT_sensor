"""Build the SQLite database from the versioned log.

    python database/build_database.py [output.db]

Creates the two tables of schema.sql and loads sensor_log.csv.gz into NPKv1.
The result (DB_01.db in the repository root by default) is the file the
Node-RED flow reads and writes, so it can be used to open the dashboard on the
recorded data, or inspected with any SQLite tool. An existing file is not
overwritten.
"""
import csv, gzip, sqlite3, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
LOG = HERE / "sensor_log.csv.gz"
SCHEMA = HERE / "schema.sql"
COLUMNS = ("timestamp", "ts_utc", "humidity", "temperature", "PH", "N", "P", "K", "conductivity", "ok")
INTEGER = {"timestamp", "ok"}
TEXT = {"ts_utc"}


def convert(name, value):
    if value == "":
        return None
    if name in TEXT:
        return value
    return int(value) if name in INTEGER else float(value)


def main():
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "DB_01.db"
    if out.exists():
        sys.exit(f"{out} already exists; it was not modified")
    con = sqlite3.connect(out)
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    with gzip.open(LOG, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = tuple(next(reader))
        if header != COLUMNS:
            sys.exit(f"unexpected columns: {header}")
        con.executemany(
            f"INSERT INTO NPKv1 ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
            ([convert(n, v) for n, v in zip(COLUMNS, row)] for row in reader))
    con.commit()
    n, first, last = con.execute("select count(*), min(ts_utc), max(ts_utc) from NPKv1").fetchone()
    con.close()
    print(f"{out}: {n} readings, {first} to {last} UTC")


if __name__ == "__main__":
    main()
