// Reproduce the Refresh button -> sqlite -> ToPlotData path offline,
// so the chart payload can be checked without a browser or a live sensor.
const { sqlite3, DB } = require('./db');

const COLUMN = process.argv[2] || 'temperature';
const QUERY = "select * from (select * from NPKv1 order by timestamp desc limit 2000) order by timestamp;";

const d = new sqlite3.Database(DB, sqlite3.OPEN_READONLY);

d.all(QUERY, (e, rows) => {
    if (e) { console.log('ERR', e.message); return; }

    const out = [{ series: [COLUMN], data: [[]], labels: [""] }];
    for (const item of rows) {
        if (item[COLUMN] === null || item[COLUMN] === undefined) { continue; }
        out[0].data[0].push({ x: item.timestamp * 1000, y: item[COLUMN] });
    }

    const pts = out[0].data[0];
    console.log('column "' + COLUMN + '": ' + rows.length + ' rows -> ' + pts.length + ' plot points');
    if (pts.length) {
        console.log('first: ' + JSON.stringify(pts[0]) + '  = ' + new Date(pts[0].x).toISOString());
        console.log('last : ' + JSON.stringify(pts[pts.length - 1]) + '  = ' + new Date(pts[pts.length - 1].x).toISOString());
    }
    d.close();
});
