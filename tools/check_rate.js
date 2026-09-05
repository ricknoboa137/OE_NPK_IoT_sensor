// Actual sampling rate, and the point counts an N-reading average would give.
const { sqlite3, DB } = require('./db');
const d = new sqlite3.Database(DB, sqlite3.OPEN_READONLY);

d.get("select sqlite_version() as v", (e, r) => {
    console.log('SQLite ' + r.v + '  (window functions need >= 3.25)');

    d.get("select count(*) as n, max(timestamp)-min(timestamp) as span from NPKv1", (e2, s) => {
        console.log('rows: ' + s.n + ', span ' + (s.span / 86400).toFixed(1) + ' days, ' +
                    'median interval ~' + (s.span / s.n).toFixed(1) + ' s\n');

        const ranges = [7, 15, 30, 90];
        let i = 0;
        const next = () => {
            if (i >= ranges.length) { d.close(); return; }
            const days = ranges[i++];
            d.get("select count(*) as n from NPKv1 where timestamp >= " +
                  "(select max(timestamp) from NPKv1) - " + (days * 86400), (e3, c) => {
                console.log(days + 'd: ' + c.n + ' raw rows -> ' +
                            'raw ' + c.n + ' pts | /5 ' + Math.ceil(c.n / 5) +
                            ' pts | /10 ' + Math.ceil(c.n / 10) + ' pts');
                next();
            });
        };
        next();
    });
});
