// Run the exact SQL the "build range query" function generates for each
// combination of range and averaging factor.
//   node tools/verify_decimation.js
const { sqlite3, DB } = require('./db');
const d = new sqlite3.Database(DB, sqlite3.OPEN_READONLY);

const COLS = "humidity, temperature, PH, N, P, K";

function buildSql(range, N) {
    const where = (range === "all") ? ""
        : " where timestamp >= strftime('%s','now') - " + (parseInt(range, 10) * 86400);
    if (N === 1) {
        return "select timestamp, " + COLS + " from NPKv1" + where + " order by timestamp;";
    }
    return "with r as (select timestamp, " + COLS + "," +
        " (row_number() over (order by timestamp) - 1)/" + N + " as g" +
        " from NPKv1" + where + ")" +
        " select cast(avg(timestamp) as integer) as timestamp," +
        " avg(humidity) as humidity, avg(temperature) as temperature, avg(PH) as PH," +
        " avg(N) as N, avg(P) as P, avg(K) as K, count(*) as n_raw" +
        " from r group by g order by timestamp;";
}

const cases = [];
for (const range of ["7", "30", "all"]) {
    for (const N of [1, 5, 10]) { cases.push([range, N]); }
}

let i = 0;
const next = () => {
    if (i >= cases.length) { d.close(); return; }
    const [range, N] = cases[i++];
    const t0 = Date.now();
    d.all(buildSql(range, N), (e, rows) => {
        if (e) { console.log(range + '/' + N + ': ERR ' + e.message); return next(); }
        if (!rows.length) { console.log(range + '/avg' + N + ': no rows'); return next(); }
        let readings = 0;
        for (const r of rows) { readings += (r.n_raw || 1); }
        const span = (rows[rows.length - 1].timestamp - rows[0].timestamp) / 86400;
        console.log(
            'range=' + range.padEnd(3) + ' avg=' + String(N).padEnd(2) +
            ' -> ' + String(rows.length).padStart(6) + ' pts/chart' +
            ' (' + String(rows.length * 6).padStart(6) + ' total)' +
            ' from ' + String(readings).padStart(6) + ' readings' +
            ', span ' + span.toFixed(1) + 'd' +
            ', ' + (Date.now() - t0) + 'ms');
        next();
    });
};
next();
