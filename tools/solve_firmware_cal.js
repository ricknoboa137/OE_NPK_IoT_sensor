// Solve the microcontroller-side correction factors from two captured samples.
//
// The firmware applies   value = A * raw + B   per channel (NpkCal.h), where
// "raw" is whatever the probe reports. So the probe's own internal constants
// are irrelevant here - we fit A and B against known reference values.
//
//   node tools/solve_firmware_cal.js [labelA] [labelB]
//
// Reference values come from tools/references.json. Fill in the true value of
// each channel for each soil (lab analysis, buffer solution, thermometer).
// Channels left null are skipped.
//
//     A = (refB - refA) / (rawB - rawA)
//     B =  refA - A * rawA
const fs = require('fs');
const path = require('path');

const SAMPLES = path.join(__dirname, 'samples.jsonl');
const REFS = path.join(__dirname, 'references.json');

const samples = fs.readFileSync(SAMPLES, 'utf8').split(String.fromCharCode(10))
    .filter(l => l.trim()).map(l => JSON.parse(l));

if (!fs.existsSync(REFS)) { console.log('missing ' + REFS); process.exit(1); }
const refs = JSON.parse(fs.readFileSync(REFS, 'utf8'));

const labelA = process.argv[2] || Object.keys(refs.soils)[0];
const labelB = process.argv[3] || Object.keys(refs.soils)[1];

const A = samples.filter(s => s.label === labelA).pop();
const B = samples.filter(s => s.label === labelB).pop();
if (!A || !B) { console.log('no capture for ' + labelA + ' or ' + labelB); process.exit(1); }

// published key -> firmware channel key (NPK_CHANNELS[].key)
const CHANNELS = {
    Humidity: 'moisture',
    Temperature: 'temperature',
    PH: 'ph',
    Nitrogen: 'nitrogen',
    Phosphorus: 'phosphorus',
    Potassium: 'potassium',
};

console.log('fitting ' + labelA + ' vs ' + labelB);
console.log('');
console.log('channel        probe A   probe B     ref A    ref B        A(gain)   B(offset)');
console.log('-'.repeat(84));

const commands = [];
const warnings = [];

for (const key of Object.keys(CHANNELS)) {
    const ch = CHANNELS[key];
    const rawA = A.stats[key] ? A.stats[key].mean : null;
    const rawB = B.stats[key] ? B.stats[key].mean : null;
    const refA = (refs.soils[labelA] || {})[ch];
    const refB = (refs.soils[labelB] || {})[ch];

    if (rawA === null || rawB === null) continue;
    if (refA === null || refA === undefined || refB === null || refB === undefined) {
        console.log(ch.padEnd(13) + String(rawA).padStart(9) + String(rawB).padStart(10) +
                    '        -         -     (no reference given)');
        continue;
    }

    const span = rawB - rawA;
    if (Math.abs(span) < 1e-6) {
        console.log(ch.padEnd(13) + String(rawA).padStart(9) + String(rawB).padStart(10) +
                    '   flat span - the probe read the same in both soils, cannot solve');
        continue;
    }

    const a = (refB - refA) / span;
    const b = refA - a * rawA;

    console.log(ch.padEnd(13) + String(rawA).padStart(9) + String(rawB).padStart(10) +
                String(refA).padStart(10) + String(refB).padStart(9) +
                a.toFixed(5).padStart(15) + b.toFixed(5).padStart(12));

    if (a < 0) {
        warnings.push(ch + ': negative gain - the probe read HIGHER where the true value ' +
                      'is LOWER. Check the reference values are not swapped.');
    }
    if (rawA === 0 || rawB === 0) {
        warnings.push(ch + ': the probe reported exactly 0 in one soil, which is often a ' +
                      'floor rather than a measurement. The fit rests on that point - treat ' +
                      'it as provisional until a third soil confirms it.');
    }
    if (Math.abs(a) > 100 || Math.abs(b) > 10000) {
        warnings.push(ch + ': implausible magnitude (A=' + a.toFixed(3) + ', B=' + b.toFixed(1) +
                      '), the two points are probably too close together.');
    }

    commands.push('cal set ' + ch + ' ' + a.toFixed(5) + ' ' + b.toFixed(5));
}

if (warnings.length) {
    console.log('');
    console.log('warnings:');
    for (const w of warnings) { console.log('  - ' + w); }
}

console.log('');
console.log('=== commands to write these into the microcontroller ===');
console.log('(paste on the serial console, or publish to NPKcommand)');
console.log('');
for (const c of commands) { console.log('  ' + c); }
console.log('');
console.log('Nothing is written to the probe itself - these live in ESP32 NVS.');
console.log('Verify afterwards with "cal", and undo with "cal clear all".');
