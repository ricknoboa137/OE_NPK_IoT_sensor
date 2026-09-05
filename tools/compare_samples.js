// Compare two captured samples and work out which registers are constants,
// which are measurements, and whether any register could be a pre-correction
// raw value for N, P or K.
//   node tools/compare_samples.js GOOD GARDENING
const fs = require('fs');
const path = require('path');

const lines = fs.readFileSync(path.join(__dirname, 'samples.jsonl'), 'utf8')
                .split(String.fromCharCode(10)).filter(l => l.trim());
const samples = lines.map(l => JSON.parse(l));

const nameA = process.argv[2] || samples[0].label;
const nameB = process.argv[3] || samples[samples.length - 1].label;
const A = samples.filter(s => s.label === nameA).pop();
const B = samples.filter(s => s.label === nameB).pop();
if (!A || !B) { console.log('sample not found'); process.exit(1); }

console.log('A = ' + A.label + '   ' + A.captured);
console.log('B = ' + B.label + '   ' + B.captured);
console.log('');

const KEYS = ['Humidity', 'Temperature', 'PH', 'Nitrogen', 'Phosphorus', 'Potassium'];
console.log('published readings:');
for (const k of KEYS) {
    const a = A.stats[k], b = B.stats[k];
    if (!a || !b) continue;
    const ratio = b.mean === 0 || a.mean === 0 ? 'n/a' : (a.mean / b.mean).toFixed(3);
    console.log('  ' + k.padEnd(12) + String(a.mean).padStart(8) + ' -> ' +
                String(b.mean).padStart(8) + '   A/B ' + ratio);
}

const addrs = [...new Set(Object.keys(A.registers).concat(Object.keys(B.registers)))].sort();
const moved = [], fixed = [];
for (const k of addrs) {
    const a = A.registers[k], b = B.registers[k];
    if (a === undefined || b === undefined) continue;
    if (a === b) { if (a !== 0) fixed.push(k); }
    else moved.push({ k, a, b });
}

console.log('');
console.log('=== registers CONSTANT across two different soils (candidates for stored constants) ===');
console.log('  ' + fixed.join(', '));

console.log('');
console.log('=== registers that MOVED (live measurements) ===');
for (const m of moved) {
    const ratio = m.b === 0 ? 'n/a' : (m.a / m.b).toFixed(3);
    console.log('  ' + m.k + '  ' + String(m.a).padStart(6) + ' -> ' +
                String(m.b).padStart(6) + '   A/B ' + ratio);
}

// Could any moving register be the pre-correction raw for N, P or K? If the
// probe applies value = raw * constant, the raw must change by the SAME ratio
// as the published value.
console.log('');
console.log('=== does any register track N, P or K proportionally? ===');
for (const k of ['Nitrogen', 'Phosphorus', 'Potassium']) {
    const a = A.stats[k].mean, b = B.stats[k].mean;
    if (!a || !b) { console.log('  ' + k + ': one sample is zero, ratio undefined - skipped'); continue; }
    const want = a / b;
    const hits = moved.filter(m => m.b !== 0 && Math.abs((m.a / m.b) - want) / want < 0.05);
    console.log('  ' + k + ': published ratio ' + want.toFixed(3) +
                (hits.length ? '' : '   -> no register matches within 5%'));
    for (const h of hits) {
        console.log('      ' + h.k + '  ratio ' + (h.a / h.b).toFixed(3) +
                    '   implied factor ' + (a / h.a).toFixed(5));
    }
}
