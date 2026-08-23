# OE_NPK_IoT_sensor

IoT soil sensor developed for Óbuda University.

Soil monitoring node built around the **VMS-3001-TR probe** (Weimengshi
five-pin soil transmitter) — moisture, temperature and pH — read over RS-485
Modbus RTU by an ESP32 and published as JSON over MQTT.

```
VMS-3001-TR   --RS-485-->  ESP32  --MQTT/JSON-->  broker  -->  dashboard
```

## Contents

| Path | What it is |
|---|---|
| [`firmware/SoilNode/`](firmware/SoilNode/) | the firmware — Modbus master, calibration, MQTT |
| [`firmware/original/`](firmware/original/) | the single-file sketch this replaced, kept for reference |

Full documentation — wiring, dependencies, register map and the calibration
procedure — is in
**[firmware/SoilNode/README.md](firmware/SoilNode/README.md)**.

## What it publishes

Topic `NPKdata`:

```json
{"Humidity":34.6,"Temperature":21.4,"PH":6.8,
 "Nitrogen":3.8,"Phosphorus":2.1,"Potassium":9.5,"ok":true}
```

`ok` is false when a register did not answer that cycle; the affected channels
then carry their last good value rather than a zero.

## Calibration

Every channel carries a linear correction `value = A * raw + B`, stored in NVS
and solved from one or two known references:

```
cal low  ph 4.00      # probe in the 4.00 buffer, let it settle
cal high ph 7.00      # probe in the 7.00 buffer -> solves A and B
cal 1p   moisture 0   # offset-only trim, keeps the existing gain
cal                   # list every channel
```

Those commands work on the serial console (115200 baud) and over MQTT — publish
to `NPKcommand`, replies come back on `NPKreply` — so the probe can be
calibrated from a dashboard without a USB cable.

## Note on the datasheet

The JXBS-3001-TR manual's register map is sparse, not the contiguous block at
`0x0000` the original sketch read, and several of its printed CRC values are
wrong. Both are documented in detail in the firmware README, along with a
`scan` command for finding out what a particular unit actually answers on.
