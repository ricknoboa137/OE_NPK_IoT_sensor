// Run the "build cal command" function node from flows.json and check every
// command line it emits is one NpkConsole.cpp actually parses.
//   node tools/test_cal_command.js
//
// The grammar is checked by tokenising rather than by regex, so the file
// stays free of backslash escapes.
const fs = require('fs');
const path = require('path');

const flows = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'flows.json'), 'utf8'));
const node = flows.find(n => n.type === 'function' && n.name === 'build cal command');
if (!node) { console.log('function node not found'); process.exit(1); }

// accepted by npkNutrientFromKey (short and long forms)
const NUTRIENTS = ['n', 'p', 'k', 'nitrogen', 'phosphorus', 'potassium'];
// accepted by npkChannelFromKey
const CHANNELS = ['moisture', 'temperature', 'conductivity', 'ph',
                  'nitrogen', 'phosphorus', 'potassium'];

const isNum = s => s !== undefined && s !== '' && isFinite(Number(s));

// mirrors NpkConsole::cmdSensor and NpkConsole::cmdCal
function parses(line) {
    const t = String(line).trim().split(/ +/);
    if (t[0] === 'sensor') {
        if (t.length === 1) return true;                       // sensor show
        if (t[1] === 'cal') {
            return t.length === 5 && NUTRIENTS.indexOf(t[2]) !== -1 &&
                   (t[3] === 'low' || t[3] === 'high') && isNum(t[4]);
        }
        if (['offset', 'factor', 'npk'].indexOf(t[1]) !== -1) return t.length === 4;
        return false;
    }
    if (t[0] === 'cal') {
        if (t.length === 1) return true;                       // cal list
        if (['low', 'high', '1p'].indexOf(t[1]) !== -1) {
            return t.length === 4 && CHANNELS.indexOf(t[2]) !== -1 && isNum(t[3]);
        }
        if (t[1] === 'clear') {
            return t.length === 3 && (CHANNELS.indexOf(t[2]) !== -1 || t[2] === 'all');
        }
        return false;
    }
    return false;
}

const store = {};
const flow = { get: k => store[k], set: (k, v) => { store[k] = v; } };
const nodeApi = { status: () => {}, warn: console.log, error: console.log };
const fn = new Function('msg', 'flow', 'node', node.func + '\nreturn null;');
const run = p => fn({ payload: p }, flow, nodeApi);

let fails = 0;
const check = (label, out, expect) => {
    const sent = out && out[0] ? out[0].payload : null;
    if (expect === null) {
        const ok = !sent;
        console.log((ok ? '  ok   ' : '  FAIL ') + label + ' -> ' + (sent || 'nothing sent'));
        if (!ok) fails++;
        return;
    }
    let ok = sent === expect;
    let why = ok ? '' : ' (expected: ' + expect + ')';
    if (ok && !parses(sent)) { ok = false; why = ' (firmware would not parse this)'; }
    console.log((ok ? '  ok   ' : '  FAIL ') + label + ' -> "' + sent + '"' + why);
    if (!ok) fails++;
};

// sanity: the checker itself must reject junk
if (parses('sensor cal nitrogen low') || parses('cal low ph') ||
    parses('sensor cal oxygen low 5') || !parses('sensor cal n low 50')) {
    console.log('grammar checker is broken'); process.exit(1);
}

console.log('guards:');
check('low with nothing selected', run('act:low'), null);
run('ch:nitrogen');
check('low without a reference', run('act:low'), null);

console.log('\nevery channel is corrected in the microcontroller:');
run('50');
const ALL = ['nitrogen', 'phosphorus', 'potassium', 'ph', 'moisture',
             'temperature', 'conductivity'];
for (const ch of ALL) {
    run('ch:' + ch);
    check(ch + ' low', run('act:low'), 'cal low ' + ch + ' 50');
    check(ch + ' high', run('act:high'), 'cal high ' + ch + ' 50');
}

console.log('\nthe probe is never written to:');
const emitted = [];
for (const ch of ALL) {
    run('ch:' + ch);
    for (const act of ['act:low', 'act:high', 'act:1p', 'act:reset', 'act:resetall']) {
        const o = run(act);
        if (o && o[0]) emitted.push(o[0].payload);
    }
}
const writesProbe = emitted.filter(c => c.indexOf('sensor factor') === 0 ||
                                        c.indexOf('sensor offset') === 0 ||
                                        c.indexOf('sensor cal') === 0 ||
                                        c.indexOf('sensor npk') === 0);
console.log((writesProbe.length === 0 ? '  ok   ' : '  FAIL ') +
            emitted.length + ' commands emitted, ' + writesProbe.length + ' write to the probe');
if (writesProbe.length) { fails++; console.log('      ' + writesProbe.join('\n      ')); }

console.log('\nreads and resets:');
run('ch:nitrogen');
check('read probe registers', run('act:sensor'), 'sensor');
check('read firmware A/B', run('act:list'), 'cal');
check('one-point trim', run('act:1p'), 'cal 1p nitrogen 50');
check('reset channel', run('act:reset'), 'cal clear nitrogen');
check('reset all', run('act:resetall'), 'cal clear all');

console.log('\ndecimal handling:');
run('ch:phosphorus'); run('4,25');
check('comma separator', run('act:high'), 'cal high phosphorus 4.25');

console.log('\nplain text, not JSON (jsonToLine has no "sensor" mapping):');
run('ch:nitrogen'); run('50');
const out = run('act:low');
const isText = out && out[0] && !String(out[0].payload).trim().startsWith('{');
console.log((isText ? '  ok   ' : '  FAIL ') + 'payload is a bare line');
if (!isText) fails++;

console.log('\n' + (fails === 0 ? 'ALL PASS' : fails + ' FAILURES'));
process.exit(fails === 0 ? 0 : 1);
