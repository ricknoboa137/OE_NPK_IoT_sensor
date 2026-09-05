// Sweep the probe's Modbus holding registers via the firmware's "scan"
// command and record what they hold. Read-only: scan issues 0x03 reads only.
//
//   node tools/scan_registers.js                 default windows
//   node tools/scan_registers.js 0x0800 0xFFFF   explicit range
//
// Results are appended to tools/scan_results.jsonl after every chunk, so a
// dropped connection or a sleeping PC costs one chunk, not the whole run.
// Addresses already in that file are skipped, so an interrupted sweep resumes
// where it stopped. (The first version of this script only wrote at the end,
// and lost 47k registers when the link dropped 50 minutes in.)
//
// Chunking: the node's MQTT reply buffer is NPK_MQTT_BUFFER-64 = 704 bytes and
// each answering register prints ~64 chars, so more than ~9 hits per reply is
// truncated. This probe answers at every address, so chunks stay at 8.
const fs = require('fs');
const path = require('path');
const mqtt = require(path.join(process.env.APPDATA, 'npm', 'node_modules',
                               'node-red', 'node_modules', 'mqtt'));

const HOST = 'mqtt://192.168.0.153:1883';
const CHUNK = 8;
const CHUNK_TIMEOUT_MS = 30000;
const JSONL = path.join(__dirname, 'scan_results.jsonl');

let WINDOWS = [
    [0x0000, 0x000F, 'measurement block'],
    [0x0020, 0x002F, 'documented factor block'],
    [0x0050, 0x005F, 'documented offset block'],
    [0x0110, 0x0133, 'undocumented calibration pairs'],
    [0x04E8, 0x0503, 'documented N/P/K factor block'],
    [0x07D0, 0x07D3, 'device config'],
];
if (process.argv.length >= 4) {
    WINDOWS = [[Number(process.argv[2]), Number(process.argv[3]), 'explicit range']];
}

const hex = n => '0x' + n.toString(16).toUpperCase().padStart(4, '0');

// ---- resume: load whatever previous runs captured ----
const seen = new Map();
if (fs.existsSync(JSONL)) {
    for (const line of fs.readFileSync(JSONL, 'utf8').split(String.fromCharCode(10))) {
        if (!line.trim()) continue;
        try { const r = JSON.parse(line); seen.set(r.a, r.v); } catch (e) { /* partial line */ }
    }
    console.log('resuming: ' + seen.size + ' registers already recorded');
}

const client = mqtt.connect(HOST, { connectTimeout: 8000, reconnectPeriod: 3000 });
let onReply = null;

client.on('message', (t, b) => { if (onReply) onReply(b.toString()); });
// a dropped link is recoverable - mqtt.js reconnects, so never exit here
client.on('error', e => console.log('  [mqtt] ' + e.message + ' (reconnecting)'));
client.on('offline', () => console.log('  [mqtt] offline'));

function scanChunk(first, last) {
    return new Promise(resolve => {
        let buf = '';
        let done = false;
        const finish = (timedOut) => {
            if (done) return;
            done = true;
            onReply = null;
            clearTimeout(timer);
            resolve({ text: buf, timedOut });
        };
        onReply = (s) => {
            buf += s;
            if (s.indexOf('Scan finished') !== -1) finish(false);
        };
        const timer = setTimeout(() => finish(true), CHUNK_TIMEOUT_MS);
        client.publish('NPKcommand', 'scan ' + first + ' ' + last);
    });
}

function parse(text) {
    const out = [];
    for (const raw of text.split(String.fromCharCode(10))) {
        const t = raw.trim().split(/ +/);
        // 0x0004 =    45  (0x002D)  signed     45   /10 4.5  /100 0.45
        if (t.length >= 4 && t[0].substring(0, 2).toLowerCase() === '0x' && t[1] === '=') {
            out.push({ a: parseInt(t[0], 16), v: Number(t[2]) });
        }
    }
    return out;
}

(async () => {
    await new Promise(res => client.on('connect', () => client.subscribe('NPKreply', res)));
    console.log('connected to ' + HOST + '  (read-only scan)');

    const sink = fs.createWriteStream(JSONL, { flags: 'a' });
    let scanned = 0, skipped = 0, retried = 0;

    for (const [first, last, why] of WINDOWS) {
        console.log('--- ' + hex(first) + '..' + hex(last) + '   ' + why);
        for (let a = first; a <= last; a += CHUNK) {
            const b = Math.min(a + CHUNK - 1, last);

            let have = true;
            for (let x = a; x <= b; x++) { if (!seen.has(x)) { have = false; break; } }
            if (have) { skipped += (b - a + 1); continue; }

            let rows = [];
            for (let attempt = 0; attempt < 3 && rows.length === 0; attempt++) {
                const { text, timedOut } = await scanChunk(a, b);
                rows = parse(text);
                if (rows.length === 0 && !timedOut) break;      // answered, nothing parsed
                if (rows.length === 0) { retried++; }
            }

            for (const r of rows) {
                seen.set(r.a, r.v);
                sink.write(JSON.stringify(r) + String.fromCharCode(10));
            }
            scanned += rows.length;

            if ((a / CHUNK) % 64 === 0) {
                const nzSoFar = [...seen.values()].filter(v => v !== 0).length;
                console.log('  at ' + hex(b) + '   ' + seen.size + ' recorded, ' +
                            nzSoFar + ' non-zero, ' + retried + ' retries');
            }
        }
    }

    sink.end();
    console.log('');
    console.log('scanned ' + scanned + ' new, skipped ' + skipped + ' already recorded');

    const addrs = [...seen.keys()].sort((x, y) => x - y);
    console.log('=== non-zero registers ===');
    for (const a of addrs) {
        if (seen.get(a) !== 0) { console.log('  ' + hex(a) + ' = ' + seen.get(a)); }
    }

    console.log('');
    console.log('=== float pairs (big-endian) in a plausible range ===');
    const f32 = (hi, lo) => {
        const bb = Buffer.alloc(4);
        bb.writeUInt16BE(hi, 0); bb.writeUInt16BE(lo, 2);
        return bb.readFloatBE(0);
    };
    for (const a of addrs) {
        if (!seen.has(a + 1)) continue;
        const hi = seen.get(a), lo = seen.get(a + 1);
        if (hi === 0 && lo === 0) continue;
        const v = f32(hi, lo);
        if (isFinite(v) && v !== 0 && Math.abs(v) >= 0.001 && Math.abs(v) <= 100000) {
            console.log('  ' + hex(a) + '/' + hex(a + 1) + ' = ' + v);
        }
    }

    const nz = addrs.filter(a => seen.get(a) !== 0).length;
    console.log('');
    console.log(seen.size + ' registers recorded, ' + nz + ' non-zero');
    client.end(true, () => process.exit(0));
})();
