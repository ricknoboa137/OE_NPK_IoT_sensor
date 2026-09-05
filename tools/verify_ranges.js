// Run the exact query the "build range query" function generates, for each
// selector option, and report point counts and span.
//   node tools/verify_ranges.js
const { sqlite3, DB } = require('./db');

const TARGET_POINTS = 1500;
const d = new sqlite3.Database(DB, sqlite3.OPEN_READONLY);

function buildQuery(days) {
    const span = days * 86400;
    const bucket = Math.max(1, Math.round(span / TARGET_POINTS));
    return {
        bucket: bucket,
        sql: "select cast(timestamp/" + bucket + " as integer)*" + bucket + " as timestamp," +
             " avg(humidity) as humidity, avg(temperature) as temperature, avg(PH) as PH," +
             " avg(N) as N, avg(P) as P, avg(K) as K" +
             " from NPKv1" +
             " where timestamp >= (select max(timestamp) from NPKv1) - " + span +
             " group by timestamp/" + bucket +
             " order by timestamp;"
    };
}

d.get("select count(*) as n, datetime(min(timestamp),'unixepoch') as first," +
      " datetime(max(timestamp),'unixepoch') as last from NPKv1", (e, r) => {
    if (e) { console.log('ERR', e.message); return; }
    console.log('table: ' + r.n + ' rows, ' + r.first + ' -> ' + r.last + ' UTC\n');

    const ranges = [7, 15, 30, 90];
    let i = 0;
    const next = () => {
        if (i >= ranges.length) { d.close(); return; }
        const days = ranges[i++];
        const q = buildQuery(days);
        d.all(q.sql, (e2, rows) => {
            if (e2) { console.log(days + 'd: ERR ' + e2.message); return next(); }
            if (!rows.length) { console.log(days + 'd: no rows'); return next(); }
            const first = new Date(rows[0].timestamp * 1000).toISOString().slice(0, 16);
            const last = new Date(rows[rows.length - 1].timestamp * 1000).toISOString().slice(0, 16);
            console.log(days + 'd: ' + rows.length + ' points, ' + q.bucket + 's buckets, ' +
                        first + ' -> ' + last +
                        ', temp ' + rows[rows.length - 1].temperature.toFixed(2));
            next();
        });
    };
    next();
});
