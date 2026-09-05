// One-shot migration, already applied. Kept for reference / re-running on a
// fresh copy: converts the original table (ms epoch, untyped) into the
// current schema (unix seconds + readable ts_utc).
//   node tools/migrate.js
const { sqlite3, DB, OLD_DB } = require('./db');

const d = new sqlite3.Database(DB);

d.serialize(() => {
    d.run("ATTACH DATABASE '" + OLD_DB.replace(/\\/g, '/') + "' AS old");

    d.run(`INSERT INTO NPKv1 (timestamp, ts_utc, humidity, temperature, PH, N, P, K)
           SELECT CAST(timestamp/1000 AS INTEGER),
                  datetime(CAST(timestamp/1000 AS INTEGER),'unixepoch'),
                  humidity, temperature, PH, N, P, K
           FROM old.NPKv1
           WHERE timestamp BETWEEN 1000000000000 AND 4000000000000`,
        function (err) {
            console.log(err ? 'INSERT ERR ' + err.message : 'migrated rows: ' + this.changes);
        });

    d.run("DETACH DATABASE old");

    d.all("select count(*) as n, min(ts_utc) as first, max(ts_utc) as last from NPKv1", (e, r) => {
        if (e) { console.log('ERR', e.message); return; }
        console.log('target now: ' + r[0].n + ' rows, ' + r[0].first + ' -> ' + r[0].last);
        d.close();
    });
});
