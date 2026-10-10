"""Where the manuscript's data live, and how the scripts open them.

All data needed to reproduce the figures and numbers of the manuscript are kept
under version control in the paper repository, in its `data/` folder (and, for
the laboratory database and the calibration workbook, where they already were).
The scripts in this folder read nothing from anywhere else.

    set PAPER_DIR=C:/path/to/Agriculture-4351955
"""
import os, csv, gzip, sqlite3, pathlib

PAPER = pathlib.Path(os.environ.get(
    "PAPER_DIR", r"C:/Users/User/Documents/GitHub/Agriculture-4351955"))
DATA = PAPER / "data"

SENSOR_LOG = DATA / "sensor_log.csv.gz"
NDMI_STACK = DATA / "ndmi_csolnok_field.npz"
STATION_DAILY = DATA / "station_csolnok_daily.csv"
FIELD_META = DATA / "ndmi_field_meta.json"
SZ24_SOURCES = DATA / "figure_sz24"
LAB_CSV = PAPER / "SZ-24/SZ-24/SZ-24_ADATBAZIS.csv"
CAL_XLSX = PAPER / "SoilSamplesCalibrationTest.xlsx"

_COLUMNS = ("timestamp", "ts_utc", "humidity", "temperature", "PH", "N", "P", "K", "conductivity", "ok")
_INT = {"timestamp", "ok"}
_TEXT = {"ts_utc"}


def log_connection():
    """The sensor log as an in-memory SQLite table named NPKv1.

    The log is stored as gzip-compressed CSV so that it can be versioned and
    read without the original database; loading it into SQLite keeps the
    queries in the analysis scripts exactly as they were written.
    """
    if not SENSOR_LOG.exists():
        raise SystemExit(f"sensor log not found: {SENSOR_LOG}\nset PAPER_DIR to a checkout of the paper repository")
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE NPKv1 (timestamp INTEGER, ts_utc TEXT, humidity REAL, temperature REAL, "
                "PH REAL, N REAL, P REAL, K REAL, conductivity REAL, ok INTEGER)")

    def convert(name, value):
        if value == "":
            return None
        if name in _TEXT:
            return value
        return int(value) if name in _INT else float(value)

    with gzip.open(SENSOR_LOG, "rt", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        if tuple(header) != _COLUMNS:
            raise SystemExit(f"unexpected columns in {SENSOR_LOG.name}: {header}")
        con.executemany("INSERT INTO NPKv1 VALUES (?,?,?,?,?,?,?,?,?,?)",
                        ([convert(n, v) for n, v in zip(_COLUMNS, row)] for row in reader))
    con.execute("CREATE INDEX ix_ts ON NPKv1(timestamp)")
    con.commit()
    return con
