// Print schema, row count and newest rows of a database.
//   node tools/inspect_db.js          -> the live DB_01.db
//   node tools/inspect_db.js --old    -> the original ms-timestamp backup
const { sqlite3, DB, OLD_DB } = require('./db');

const target = process.argv.includes('--old') ? OLD_DB : DB;
console.log('database: ' + target);

const d = new sqlite3.Database(target, sqlite3.OPEN_READONLY);

d.all("select name, sql from sqlite_master where type='table'", (e, tables) => {
    if (e) { console.log('ERR', e.message); return; }
    let i = 0;
    const next = () => {
        if (i >= tables.length) { d.close(); return; }
        const t = tables[i++];
        console.log('\n=== ' + t.name + ' ===');
        console.log(t.sql);
        d.all('select count(*) as n from "' + t.name + '"', (e2, c) => {
            console.log('rows: ' + (e2 ? 'ERR ' + e2.message : c[0].n));
            d.all('select * from "' + t.name + '" order by rowid desc limit 3', (e3, r) => {
                if (!e3) { console.log('-- newest:'); r.forEach(x => console.log('  ' + JSON.stringify(x))); }
                next();
            });
        });
    };
    next();
});
