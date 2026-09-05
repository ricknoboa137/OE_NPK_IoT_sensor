// Exercise the backup/restore function nodes from flows.json against the real
// register dump this probe returned, without touching the hardware.
//   node tools/test_cal_backup.js
const fs = require('fs');
const path = require('path');

const flows = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'flows.json'), 'utf8'));
const pick = name => {
    const n = flows.find(x => x.type === 'function' && x.name === name);
    if (!n) { console.log('missing function node: ' + name); process.exit(1); }
    return new Function('msg', 'flow', 'node', n.func + '\nreturn null;');
};

const parseFn = pick('parse sensor dump');
const resultFn = pick('restore or list');
const controlFn = pick('backup control');

const NL = String.fromCharCode(10);

// verbatim from the probe (tools/mqtt_probe.js output)
const DUMP = [
    '',
    'Sensor-side calibration (stored in the probe, not the ESP32)',
    '  0x0022  conductivity factor       0   factory default 0',
    '  0x0023  salinity factor          55   factory default 55',
    '  0x0024  TDS factor               50   factory default 50',
    '',
    '  0x0050  temperature offset   raw      0  -> 0.00',
    '  0x0051  humidity offset      raw      0  -> 0.00',
    '  0x0052  conductivity offset  raw      0  -> 0.00',
    '  0x0053  pH offset            raw      0  -> 0.00',
    '  0x04E8  n factor 0.00000   offset 0',
    '  0x04F2  p factor 0.00000   offset 0',
    '  0x04FC  k factor 0.00000   offset 0',
    '',
    'The manual documents factory defaults only for 0x0022-0x0024.',
].join(NL);

// a calibrated-looking dump, to prove non-zero values survive the round trip
const DUMP2 = [
    'Sensor-side calibration (stored in the probe, not the ESP32)',
    '  0x0022  conductivity factor       0   factory default 0',
    '  0x0050  temperature offset   raw     -12  -> -1.20',
    '  0x0051  humidity offset      raw      35  -> 3.50',
    '  0x0052  conductivity offset  raw       0  -> 0.00',
    '  0x0053  pH offset            raw      -3  -> -3.00',
    '  0x04E8  n factor 1.23456   offset 7',
    '  0x04F2  p factor no reply   offset no reply',
    '  0x04FC  k factor 0.98765   offset -2',
].join(NL);

let fails = 0;
const ok = (cond, label, extra) => {
    console.log((cond ? '  ok   ' : '  FAIL ') + label + (extra ? '  ' + extra : ''));
    if (!cond) fails++;
};

const mkctx = (init) => {
    const store = Object.assign({}, init);
    return {
        store,
        flow: { get: k => store[k], set: (k, v) => { store[k] = v; } },
        node: { status: () => {}, warn: () => {}, error: () => {} },
    };
};

console.log('parser only fires when a backup was asked for:');
let c = mkctx({});
ok(parseFn({ payload: DUMP }, c.flow, c.node) === null,
   'unrequested dump is ignored');
c = mkctx({ pendingBackup: 123 });
ok(parseFn({ payload: 'some other reply' }, c.flow, c.node) === null,
   'non-dump reply is ignored');
ok(c.store.pendingBackup === 123, 'and the pending flag survives it');

console.log('\nparsing the real dump:');
c = mkctx({ pendingBackup: Date.now() });
let out = parseFn({ payload: DUMP }, c.flow, c.node);
ok(Array.isArray(out) && out[0] && out[0].params, 'produced an insert row');
const snap = JSON.parse(out[0].params.$data);
ok(JSON.stringify(snap.factors) === '{"n":0,"p":0,"k":0}', 'n/p/k factors', JSON.stringify(snap.factors));
ok(JSON.stringify(snap.offsets) === '{"temp":0,"hum":0,"ec":0,"ph":0}', 'four offsets', JSON.stringify(snap.offsets));
ok(snap.readonly.salinity_factor === 55 && snap.readonly.tds_factor === 50,
   'read-only factory registers captured', JSON.stringify(snap.readonly));
ok(c.store.pendingBackup === null, 'pending flag cleared, so one press = one snapshot');
ok(typeof out[0].params.$ts_utc === 'string' && out[0].params.$ts_utc.length === 19,
   'timestamp column', out[0].params.$ts_utc);

console.log('\nparsing a calibrated dump with unreadable registers:');
c = mkctx({ pendingBackup: 1 });
out = parseFn({ payload: DUMP2 }, c.flow, c.node);
const snap2 = JSON.parse(out[0].params.$data);
ok(snap2.factors.n === 1.23456 && snap2.factors.k === 0.98765, 'non-zero gains kept', JSON.stringify(snap2.factors));
ok(snap2.factors.p === undefined, 'unreadable gain not invented');
ok(snap2.unread.indexOf('0X04F2') !== -1, 'unreadable register recorded', JSON.stringify(snap2.unread));
ok(snap2.offsets.temp === -12 && snap2.offsets.ph === -3, 'negative offsets kept', JSON.stringify(snap2.offsets));

console.log('\ncontrol buttons:');
c = mkctx({});
out = controlFn({ payload: 'act:backup' }, c.flow, c.node);
ok(out[0].payload === 'sensor' && typeof c.store.pendingBackup === 'number',
   'backup asks for a dump and arms the parser');
out = controlFn({ payload: 'act:restore' }, c.flow, c.node);
ok(out[1].topic.indexOf('order by ts limit 1') !== -1 && c.store.restoreMode === 'apply',
   'restore reads the OLDEST snapshot', out[1].topic);
out = controlFn({ payload: 'act:backups' }, c.flow, c.node);
ok(c.store.restoreMode === 'list', 'list mode set');

console.log('\nrestore from the captured snapshot:');
c = mkctx({ restoreMode: 'apply' });
const row = [{ ts: 1, ts_utc: '2026-08-23 20:10:00', note: 'x', data: JSON.stringify(snap2) }];
out = resultFn({ payload: row }, c.flow, c.node);
const cmds = out[0].map(m => m.payload);
console.log('       ' + cmds.join(NL + '       '));
ok(cmds.indexOf('sensor factor n 1.23456') !== -1, 'gain restored');
ok(cmds.indexOf('sensor factor k 0.98765') !== -1, 'second gain restored');
ok(cmds.every(c2 => c2.indexOf('sensor factor p') === -1), 'unreadable gain not written back');
ok(cmds.indexOf('sensor offset temp -12') !== -1, 'offset restored');
ok(cmds.indexOf('sensor offset ph -3') !== -1, 'negative offset restored');
ok(out[1].payload.line.indexOf('not restorable') !== -1, 'says what it cannot restore');

// every generated command must be one the firmware parses
const NUTS = ['n', 'p', 'k'];
const OFFS = ['temp', 'hum', 'ec', 'ph'];
const good = cmds.every(line => {
    const t = line.split(/ +/);
    if (t[0] !== 'sensor') return false;
    if (t[1] === 'factor') return t.length === 4 && NUTS.indexOf(t[2]) !== -1 && isFinite(Number(t[3]));
    if (t[1] === 'offset') return t.length === 4 && OFFS.indexOf(t[2]) !== -1 &&
                                  Number.isInteger(Number(t[3]));
    return false;
});
ok(good, 'every command matches the firmware grammar');

console.log('\nzero-gain warning and empty table:');
c = mkctx({ restoreMode: 'apply' });
out = resultFn({ payload: [{ ts: 1, ts_utc: 'x', note: 'y', data: JSON.stringify(snap) }] }, c.flow, c.node);
ok(out[1].payload.line.indexOf('cannot run until it is set to 1.0') !== -1,
   'warns that a restored 0 gain blocks calibration');
c = mkctx({ restoreMode: 'apply' });
out = resultFn({ payload: [] }, c.flow, c.node);
ok(out[1].payload.kind === 'error', 'empty table reports cleanly');

console.log('\n' + (fails === 0 ? 'ALL PASS' : fails + ' FAILURES'));
process.exit(fails === 0 ? 0 : 1);
