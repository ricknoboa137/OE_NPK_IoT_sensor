# Register scan findings — CWT 5-pin probe, 2026-08-24

**Full 16-bit sweep complete.** All 65536 addresses read: 46 non-zero.
Above `0x07FF` there are only `0x0820 = 403` and `0x55AA = 85`.
There is no second N/P/K factor block anywhere on the device.

Read-only sweep of `0x0000`–`0x07FF` (2048 registers) via the firmware's
`scan` command. Raw data in `scan_results.json`, full log in `scan_full.log`,
manual text in `manual_text.txt`.

Every address answered, including ones the manual never mentions — this unit
returns `0` for unimplemented registers rather than a Modbus exception. So
"the register answered" proves nothing about whether it exists. 44 of 2048
were non-zero.

## The documented factor registers are genuinely empty

    0x04E8/0x04E9  N factor (float)   = 0.0     0x04EA  N offset = 0
    0x04F2/0x04F3  P factor (float)   = 0.0     0x04F4  P offset = 0
    0x04FC/0x04FD  K factor (float)   = 0.0     0x04FE  K offset = 0

Manual page 4 documents exactly these addresses, and they are where
`NpkConfig.h` points. Nothing is hidden there — the whole `0x04E8`–`0x0503`
block reads zero.

## Undocumented calibration data exists elsewhere

Three evenly spaced blocks, each holding two IEEE-754 floats (big-endian word
order, same as the documented factors):

    0x0110/0x0111 = 1372.0     0x0112/0x0113 = 40.0
    0x0120/0x0121 = 2366.0     0x0122/0x0123 = 70.0
    0x0130/0x0131 = 2846.0     0x0132/0x0133 = 90.0

The shape is (raw count, reference concentration) — 40/70/90 mg/kg are
ordinary standard-solution values.

**The nitrogen mapping is NOT confirmed** (earlier note here said it was).

    0x0009 = 1543   ->   1543 * (40 / 1372) = 44.99   published Nitrogen = 45

That looks compelling, but it does not survive scrutiny:

- Nitrogen is already available directly at `0x0004 = 45`. The published value
  needs no derivation from `0x0009`.
- A brute-force search over all 46 non-zero registers against all three pairs
  finds `0x0009` matches within 2% through the `0x0120` pair too (45.65). Two
  different "explanations" for the same value means neither is evidence.
- The three repeated samples proved only that the numbers were stable while the
  probe sat undisturbed. Identical readings repeated three times are one
  observation, not three.

A real test needs the reading to *change* - disturb the probe, then check
whether `0x0009` and Nitrogen still track through the same ratio.

**P and K have no explanation at all.** Searching every non-zero register
against every pair, with plain, /10 and /100 scalings, nothing produces 152 or
145 except the measurement registers `0x0005` and `0x0006` themselves.

So what the `0x0110`/`0x0120`/`0x0130` blocks do is still unknown. They are the
only calibration-shaped data on the device, and the values (40/70/90 against
raws 1372/2366/2846) still look like standard concentrations - but no
demonstrated link to the published readings exists.

## Other near-unity floats, purpose unknown

    0x0010/0x0011 = 1.504      0x0025/0x0026 = 1.200
    0x0045/0x0046 = 1.000      0x0150/0x0151 = 1.000
    0x0190/0x0191 = 1.486      0x0210/0x0211 = 1.023

## Practical implication

`sensor cal` and `sensor factor` write the *documented* registers
(`0x04E8`...). If this unit actually applies the undocumented `0x0110` block
instead, those writes may be inert. Before trusting probe-side calibration:
write a gain, read it back, and check whether a published reading actually
moves. If it does not, the calibration has to happen in the firmware layer
(`cal ...`) instead.

## Cost of a wider sweep

Roughly 16 registers/second over MQTT (chunks of 8, no timeouts because every
address answers). The full 16-bit space would take about 70 minutes.

## Two-soil comparison, 2026-08-24 (GOOD farm soil vs GARDENING soil)

Captured with `tools/capture_sample.js`, compared with `tools/compare_samples.js`.
Readings differed strongly: N 45 -> 0, P 151 -> 36, K 144 -> 28, pH 8.1 -> 7.2.

**`0x0009` is a constant, not raw nitrogen.** It read exactly 1543 in both
soils while nitrogen went 45 -> 0. This kills the retracted hypothesis for good.

**The three pair blocks are stored constants.** `0x0110`/`0x0120`/`0x0130`
were bit-identical across two very different soils, as were `0x0025/0x0026`
(1.2), `0x0045` (1.0), `0x0150` (1.0) and `0x0210/0x0211` (1.023).

**No register exposes a pre-correction raw N/P/K.** If the probe computed
`value = raw * factor`, the raw would have to change by the same ratio as the
published value (P 4.23x, K 5.15x). Searching every register that moved, the
only ones matching are `0x0005` and `0x0006` - which *are* the published
values. Everything else moves by a different ratio.

### Consequence for solving the constants

Two soils cannot determine the stored constants. Only corrected outputs are
visible, so for any assumed constant there is a raw value that fits - the
system is underdetermined no matter how many soils are measured.

The constants can only be found by *perturbation*: change one by a known
amount and watch what the output does. Write `sensor factor p 2.0` and see
whether published P doubles (36 -> 72).

  - output doubles  -> the documented registers are live, semantics confirmed
  - output unchanged -> the documented registers are inert on this unit, and
    the real constants are the `0x0110` blocks, which have no write command in
    the firmware today

Use P or K for this, not N: nitrogen reads 0 in the gardening soil, and zero
times any factor is still zero.
