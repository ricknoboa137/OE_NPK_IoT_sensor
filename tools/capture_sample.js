// Capture a labelled soil sample: the published payload plus every register
// that has ever read non-zero, so two samples can be compared later.
//
//   node tools/capture_sample.js "GOOD - Szolnok farm"
//
// Appends one JSON object per run to tools/samples.jsonl. Read-only.
const fs = require('fs');
const path = require('path');
const mqtt = require(path.join(process.env.APPDATA, 'npm', 'node_modules',
                               'node-red', 'node_modules', 'mqtt'));

const HOST = 'mqtt://192.168.0.153:1883';
const OUT = path.join(__dirname, 'samples.jsonl');
const LABEL = process.argv[2] || 'unlabelled';
const NOTE = process.argv[3] || '';

// windows worth recording: the measurement block, everything that read
// non-zero in the full sweep, and the documented calibration registers
const WINDOWS = [
    [0x0000, 0x0015], [0x001D, 0x001E], [0x0022, 0x0026],
    [0x0045, 0x0046], [0x00F0, 0x00F0], [0x00FF, 0x0100],
    [0x0110, 0x0133], [0x0150, 0x0151], [0x0190, 0x0191],
    [0x0210, 0x0211], [0x04E8, 0x04FE], [0x07D0, 0x07D4],
];
const CHUNK = 8;

const client = mqtt.connect(HOST, { connectTimeout: 8000, reconnectPeriod: 3000 });
let onReply = null;
const payloads = [];

client.on('message', (t, b) => {
    const s = b.toString();
    if (t === 'NPKdata') { payloads.push(s); }
    else if (onReply) { onReply(s); }
});
client.on('error', e => console.log('  [mqtt] ' + e.message));

function scanChunk(first, last) {
    return new Promise(resolve => {
        let buf = '', done = false;
        const finish = () => {
            if (done) return;
            done = true; onReply = null; clearTimeout(timer); resolve(buf);
        };
        onReply = s => { buf += s; if (s.indexOf('Scan finished') !== -1) finish(); };
        const timer = setTimeout(finish, 30000);
        client.publish('NPKcommand', 'scan ' + first + ' ' + last);
    });
}

function parse(text, into) {
    for (const raw of text.split(String.fromCharCode(10))) {
        const t = raw.trim().split(/ +/);
        if (t.length >= 4 && t[0].substring(0, 2).toLowerCase() === '0x' && t[1] === '=') {
            into[t[0].toUpperCase()] = Number(t[2]);
        }
    }
}

(async () => {
    await new Promise(res => client.on('connect', () => client.subscribe(['NPKdata', 'NPKreply'], res)));
    console.log('label: ' + LABEL);
    console.log('collecting published readings...');

    // let a few payloads arrive first so the reading is not a single sample
    await new Promise(r => setTimeout(r, 16000));

    const regs = {};
    process.stdout.write('reading registers');
    for (const [first, last] of WINDOWS) {
        for (let a = first; a <= last; a += CHUNK) {
            const b = Math.min(a + CHUNK - 1, last);
            parse(await scanChunk(a, b), regs);
            process.stdout.write('.');
        }
    }
    console.log('');

    // a couple more payloads after the scan, to show whether it drifted
    await new Promise(r => setTimeout(r, 12000));

    const parsed = payloads.map(p => { try { return JSON.parse(p); } catch (e) { return null; } })
                           .filter(Boolean);
    const keys = ['Humidity', 'Temperature', 'Conductivity', 'PH', 'Nitrogen', 'Phosphorus', 'Potassium'];
    const stats = {};
    for (const k of keys) {
        const vals = parsed.map(p => p[k]).filter(v => typeof v === 'number');
        if (!vals.length) continue;
        stats[k] = {
            min: Math.min.apply(null, vals),
            max: Math.max.apply(null, vals),
            mean: Number((vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(3)),
            n: vals.length,
        };
    }

    const sample = {
        label: LABEL,
        note: NOTE,
        captured: new Date().toISOString(),
        payloads: parsed,
        stats: stats,
        registers: regs,
    };
    fs.appendFileSync(OUT, JSON.stringify(sample) + String.fromCharCode(10));

    console.log('');
    console.log('published readings (' + parsed.length + ' messages):');
    for (const k of keys) {
        if (!stats[k]) continue;
        const s = stats[k];
        console.log('  ' + k.padEnd(13) + ' mean ' + String(s.mean).padStart(8) +
                    '   range ' + s.min + ' .. ' + s.max);
    }
    console.log('');
    console.log('non-zero registers:');
    for (const k of Object.keys(regs).sort()) {
        if (regs[k] !== 0) { console.log('  ' + k + ' = ' + regs[k]); }
    }
    console.log('');
    console.log('appended to tools/samples.jsonl');
    client.end(true, () => process.exit(0));
})();
