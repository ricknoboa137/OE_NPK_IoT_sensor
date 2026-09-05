// The table now holds two separate blocks of data. Describe each.
const { sqlite3, DB } = require('./db');
const d = new sqlite3.Database(DB, sqlite3.OPEN_READONLY);

const SPLIT = "2026-06-01";   // anything after this is from the new machine

const q = (label, where) => new Promise((res) => {
    d.get("select count(*) as n, datetime(min(timestamp),'unixepoch') as first," +
          " datetime(max(timestamp),'unixepoch') as last," +
          " (max(timestamp)-min(timestamp)) as span from NPKv1 where " + where, (e, r) => {
        if (e || !r.n) { console.log(label + ': none'); return res(); }
        console.log(label + ': ' + r.n + ' rows, ' + r.first + ' -> ' + r.last +
                    ', avg interval ' + (r.span / (r.n - 1)).toFixed(1) + ' s');
        res();
    });
});

(async () => {
    await q('archive (Jan)', "timestamp < strftime('%s','" + SPLIT + "')");
    await q('live (new)   ', "timestamp >= strftime('%s','" + SPLIT + "')");
    d.get("select datetime('now') as now", (e, r) => {
        console.log('now: ' + r.now + ' UTC');
        d.close();
    });
})();
