// Reproduce the "point count" function's output for each selector option.
//   node tools/verify_count_text.js
const { sqlite3, DB } = require('./db');

const d = new sqlite3.Database(DB, sqlite3.OPEN_READONLY);
const TARGET_POINTS = 1500;

function summarise(rows, days) {
    if (rows.length === 0) { return "no data in the last " + days + " days"; }
    const fmt = (s) => new Date(s * 1000).toISOString().slice(0, 10);
    const first = rows[0].timestamp, last = rows[rows.length - 1].timestamp;
    const perChart = rows.length;
    const bucketSecs = rows.length > 1 ? Math.round((last - first) / (rows.length - 1)) : 0;
    const bucketTxt = bucketSecs >= 3600
        ? (bucketSecs / 3600).toFixed(1) + " h"
        : Math.round(bucketSecs / 60) + " min";
    return perChart + " points/chart (" + (perChart * 6) + " total) · " +
           bucketTxt + " avg · " + fmt(first) + " to " + fmt(last);
}

const ranges = [7, 15, 30, 90];
let i = 0;
const next = () => {
    if (i >= ranges.length) { d.close(); return; }
    const days = ranges[i++];
    const span = days * 86400;
    const bucket = Math.max(1, Math.round(span / TARGET_POINTS));
    const sql = "select cast(timestamp/" + bucket + " as integer)*" + bucket + " as timestamp," +
        " avg(temperature) as temperature from NPKv1" +
        " where timestamp >= (select max(timestamp) from NPKv1) - " + span +
        " group by timestamp/" + bucket + " order by timestamp;";
    d.all(sql, (e, rows) => {
        console.log(days + 'd -> "' + (e ? 'ERR ' + e.message : summarise(rows, days)) + '"');
        next();
    });
};
next();
