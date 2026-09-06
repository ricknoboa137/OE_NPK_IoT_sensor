// Solve the microcontroller-side correction factors from captured samples.
//
// The firmware applies   value = A * raw + B   per channel (NpkCal.h), where
// "raw" is whatever the probe reports. So the probe's own internal constants
// are irrelevant here - we fit A and B against known reference values.
//
//   node tools/solve_firmware_cal.js [labelA] [labelB]
//
// Labels match by PREFIX, case-insensitively, so "GOOD" pools every capture
// labelled GOOD, GOOD-1, "GOOD spot 3" and so on. That matters: each run of
// capture_sample.js is one insertion of the probe, and the spread BETWEEN
// insertions is the real uncertainty. Repeated readings from a probe left
// sitting in the soil are one observation, not many.
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
const NL = String.fromCharCode(10);

const samples = fs.readFileSync(SAMPLES, 'utf8').split(NL)
    .filter(l => l.trim()).map(l => JSON.parse(l));

if (!fs.existsSync(REFS)) { console.log('missing ' + REFS); process.exit(1); }
const refs = JSON.parse(fs.readFileSync(REFS, 'utf8'));

const labelA = process.argv[2] || Object.keys(refs.soils)[0];
const labelB = process.argv[3] || Object.keys(refs.soils)[1];

// published key -> firmware channel key (NPK_CHANNELS[].key)
const CHANNELS = {
    Humidity: 'moisture',
    Temperature: 'temperature',
    PH: 'ph',
    Nitrogen: 'nitrogen',
    Phosphorus: 'phosphorus',
    Potassium: 'potassium',
};

function mean(xs) { return xs.reduce((a, b) => a + b, 0) / xs.length; }
function sd(xs) {
    if (xs.length < 2) return 0;
    const m = mean(xs);
    return Math.sqrt(xs.reduce((a, x) => a + (x - m) * (x - m), 0) / (xs.length - 1));
}

// Every capture whose label starts with the given prefix, oldest first.
function insertionsFor(prefix) {
    const p = prefix.toLowerCase();
    return samples.filter(s => String(s.label).toLowerCase().indexOf(p) === 0);
}

// Per channel: one value per insertion (that insertion's own mean), plus the
// scatter within each insertion for comparison.
function gather(insertions, publishedKey) {
    const perInsertion = [];
    const withinSds = [];
    for (const ins of insertions) {
        const vals = [];
        for (const raw of (ins.payloads || [])) {
            let obj;
            try { obj = JSON.parse(raw); } catch (e) { continue; }
            if (typeof obj[publishedKey] === 'number') vals.push(obj[publishedKey]);
        }
        if (!vals.length && ins.stats && ins.stats[publishedKey]) {
            perInsertion.push(ins.stats[publishedKey].mean);   // older capture format
            continue;
        }
        if (!vals.length) continue;
        perInsertion.push(mean(vals));
        withinSds.push(sd(vals));
    }
    return {
        n: perInsertion.length,
        mean: perInsertion.length ? mean(perInsertion) : null,
        between: sd(perInsertion),
        within: withinSds.length ? mean(withinSds) : 0,
        values: perInsertion,
    };
}

const insA = insertionsFor(labelA);
const insB = insertionsFor(labelB);
if (!insA.length || !insB.length) {
    console.log('no captures matching "' + labelA + '" or "' + labelB + '"');
    console.log('labels present: ' + samples.map(s => s.label).join(', '));
    process.exit(1);
}

console.log('fitting ' + labelA + ' (' + insA.length + ' insertion' +
            (insA.length === 1 ? '' : 's') + ') vs ' +
            labelB + ' (' + insB.length + ' insertion' +
            (insB.length === 1 ? '' : 's') + ')');
if (insA.length === 1 || insB.length === 1) {
    console.log('');
    console.log('  Only one insertion for at least one soil, so there is no estimate of');
    console.log('  placement uncertainty - the dominant error for a probe reading a');
    console.log('  5 cm sphere of heterogeneous soil. Capture several insertions at');
    console.log('  different spots and re-run to see how much the fit actually moves.');
}
console.log('');

const commands = [];
const warnings = [];

for (const key of Object.keys(CHANNELS)) {
    const ch = CHANNELS[key];
    const refA = (refs.soils[labelA] || {})[ch];
    const refB = (refs.soils[labelB] || {})[ch];
    if (refA === null || refA === undefined || refB === null || refB === undefined) continue;

    const gA = gather(insA, key);
    const gB = gather(insB, key);
    if (gA.mean === null || gB.mean === null) continue;

    console.log(ch);
    console.log('  ' + labelA.padEnd(10) + ' probe ' + gA.mean.toFixed(2).padStart(8) +
                '   between-insertion SD ' + gA.between.toFixed(2).padStart(6) +
                '   within ' + gA.within.toFixed(2) +
                '   ref ' + refA);
    console.log('  ' + labelB.padEnd(10) + ' probe ' + gB.mean.toFixed(2).padStart(8) +
                '   between-insertion SD ' + gB.between.toFixed(2).padStart(6) +
                '   within ' + gB.within.toFixed(2) +
                '   ref ' + refB);

    const span = gB.mean - gA.mean;
    if (Math.abs(span) < 1e-6) {
        console.log('  flat span - the probe read the same in both soils, cannot solve');
        console.log('');
        continue;
    }

    const a = (refB - refA) / span;
    const b = refA - a * gA.mean;
    console.log('  A = ' + a.toFixed(5) + '   B = ' + b.toFixed(5));

    // How much does placement uncertainty move the answer? Evaluate the fit at
    // the four corners of +/- one between-insertion SD on each soil.
    if (gA.between > 0 || gB.between > 0) {
        const as = [], bs = [];
        for (const da of [-gA.between, gA.between]) {
            for (const db of [-gB.between, gB.between]) {
                const s2 = (gB.mean + db) - (gA.mean + da);
                if (Math.abs(s2) < 1e-6) continue;
                const a2 = (refB - refA) / s2;
                as.push(a2);
                bs.push(refA - a2 * (gA.mean + da));
            }
        }
        if (as.length) {
            console.log('  at +/-1 SD on placement:  A ' + Math.min(...as).toFixed(5) +
                        ' .. ' + Math.max(...as).toFixed(5) +
                        '   B ' + Math.min(...bs).toFixed(2) +
                        ' .. ' + Math.max(...bs).toFixed(2));
        }
    }
    console.log('');

    if (a < 0) {
        warnings.push(ch + ': negative gain - the probe read HIGHER where the true value ' +
                      'is LOWER. Check the reference values are not swapped.');
    }
    if (gA.mean === 0 || gB.mean === 0) {
        warnings.push(ch + ': the probe reported exactly 0 in one soil, which is often a ' +
                      'floor rather than a measurement. B then equals that soil\'s ' +
                      'reference exactly, so every future soil that bottoms out will be ' +
                      'reported as ' + b.toFixed(1) + ' - asserted, not measured.');
    }
    if (b < 0) {
        warnings.push(ch + ': B is negative, so any raw reading below ' + (-b / a).toFixed(1) +
                      ' produces a negative result. The firmware range check drops those ' +
                      'from NPKdata rather than publishing them, so expect gaps whenever ' +
                      'this channel reads low.');
    }
    if (Math.abs(a) > 100 || Math.abs(b) > 10000) {
        warnings.push(ch + ': implausible magnitude (A=' + a.toFixed(3) + ', B=' + b.toFixed(1) +
                      '), the two points are probably too close together.');
    }

    commands.push('cal set ' + ch + ' ' + a.toFixed(5) + ' ' + b.toFixed(5));
}

// Moisture and temperature are not being calibrated, but they shape the NPK
// reading, so a mismatch between the two soils is a confound worth seeing.
for (const [key, what] of [['Humidity', 'moisture'], ['Temperature', 'temperature']]) {
    const gA = gather(insA, key), gB = gather(insB, key);
    if (gA.mean === null || gB.mean === null) continue;
    const diff = Math.abs(gA.mean - gB.mean);
    const limit = key === 'Humidity' ? 3 : 2;
    if (diff > limit) {
        warnings.push('the two soils differ by ' + diff.toFixed(1) + ' in ' + what +
                      ' (' + gA.mean.toFixed(1) + ' vs ' + gB.mean.toFixed(1) + '). ' +
                      'These probes derive NPK indirectly, so part of what the fit ' +
                      'attributes to nutrient content may be a ' + what + ' difference.');
    }
}

if (warnings.length) {
    console.log('warnings:');
    for (const w of warnings) { console.log('  - ' + w); }
    console.log('');
}

console.log('=== commands to write these into the microcontroller ===');
console.log('(paste on the serial console, or publish to NPKcommand)');
console.log('');
for (const c of commands) { console.log('  ' + c); }
console.log('');
console.log('Nothing is written to the probe itself - these live in ESP32 NVS.');
console.log('Verify afterwards with "cal", and undo with "cal clear all".');
console.log('');
console.log('Note: two soils fit two coefficients, so the fit passes through both');
console.log('points exactly by construction. That is arithmetic, not agreement -');
console.log('it says nothing about whether the response is actually linear. A');
console.log('third soil, held back and predicted, is the only thing that tests it.');
