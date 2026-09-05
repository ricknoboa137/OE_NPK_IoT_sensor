// Current table schema and row count, ahead of adding the conductivity channel.
const { sqlite3, DB } = require('./db');
const d = new sqlite3.Database(DB, sqlite3.OPEN_READONLY);

d.all("pragma table_info(NPKv1)", (e, cols) => {
    if (e) { console.log('ERR', e.message); return; }
    console.log('columns: ' + cols.map(c => c.name + ' ' + (c.type || '-')).join(', '));
    d.get("select count(*) as n, datetime(min(timestamp),'unixepoch') as first," +
          " datetime(max(timestamp),'unixepoch') as last from NPKv1", (e2, r) => {
        console.log('rows: ' + r.n + ', ' + r.first + ' -> ' + r.last);
        d.close();
    });
});
