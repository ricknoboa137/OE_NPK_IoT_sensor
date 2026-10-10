-- Tables used by the Node-RED flow (flows.json). The flow creates both of them
-- if they do not exist, so this file is a reference and is also used by
-- build_database.py.

-- One row per reading published by the module on the MQTT topic NPKdata.
CREATE TABLE IF NOT EXISTS NPKv1 (
    timestamp    INTEGER,   -- Unix time in seconds (UTC)
    ts_utc       TEXT,      -- the same instant as 'YYYY-MM-DD HH:MM:SS' (UTC)
    humidity     REAL,      -- soil moisture, %RH
    temperature  REAL,      -- degrees Celsius
    PH           REAL,
    N            REAL,      -- mg/kg
    P            REAL,      -- mg/kg
    K            REAL,      -- mg/kg
    conductivity REAL,      -- uS/cm; this probe always reports 0
    ok           INTEGER    -- 1 when every register answered in that cycle
);

-- Copies of the calibration stored in the node, saved from the dashboard.
CREATE TABLE IF NOT EXISTS probe_cal_backup (
    ts     INTEGER,
    ts_utc TEXT,
    note   TEXT,
    data   TEXT
);
