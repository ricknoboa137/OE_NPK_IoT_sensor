// Additive migration: the SoilNode firmware publishes Conductivity and an
// `ok` flag that the old table has nowhere to put. Existing rows keep NULL.
//   node tools/add_conductivity_column.js
const { sqlite3, DB } = require('./db');
const d = new sqlite3.Database(DB);

d.all("pragma table_info(NPKv1)", (e, cols) => {
    if (e) { console.log('ERR', e.message); return; }
    const have = cols.map(c => c.name);
    const wanted = [['conductivity', 'REAL'], ['ok', 'INTEGER']];
    const missing = wanted.filter(w => have.indexOf(w[0]) === -1);

    if (missing.length === 0) { console.log('nothing to do: ' + have.join(', ')); return d.close(); }

    let i = 0;
    const next = () => {
        if (i >= missing.length) {
            d.all("pragma table_info(NPKv1)", (e3, c2) => {
                console.log('columns now: ' + c2.map(c => c.name).join(', '));
                d.close();
            });
            return;
        }
        const [name, type] = missing[i++];
        d.run('ALTER TABLE NPKv1 ADD COLUMN ' + name + ' ' + type, (e2) => {
            console.log(e2 ? 'ERR adding ' + name + ': ' + e2.message : 'added ' + name + ' ' + type);
            next();
        });
    };
    next();
});
