# OE_NPK_IoT_sensor

IoT soil sensor developed for Óbuda University.

Soil monitoring node built around the **CWT soil sensor (NPK type)** five-pin
probe — moisture, temperature, pH, nitrogen, phosphorus and potassium — read
over RS-485 Modbus RTU by an ESP32 and published as JSON over MQTT.

```
CWT NPK probe  --RS-485-->  ESP32  --MQTT/JSON-->  broker  -->  dashboard
```

## Contents

| Path | What it is |
|---|---|
| [`firmware/SoilNode/`](firmware/SoilNode/) | the firmware — Modbus master, calibration, MQTT |
| [`firmware/original/`](firmware/original/) | the single-file sketch this replaced, kept for reference |

The probe's manual is in the firmware folder. Full documentation — wiring,
dependencies, register map and the calibration procedure — is in
**[firmware/SoilNode/README.md](firmware/SoilNode/README.md)**.

## What it publishes

Topic `NPKdata`:

```json
{"Humidity":34.6,"Temperature":21.4,"Conductivity":0,"PH":6.8,
 "Nitrogen":38,"Phosphorus":21,"Potassium":95,"ok":true}
```

`ok` is false when a register did not answer that cycle; the affected channels
then carry their last good value rather than a zero.

Conductivity always reads **0.0** on this unit — the register answers, but the
probe does not measure it. That is expected, not a fault.

## Calibration

Two independent layers, and it is worth knowing which you are using.

**In the firmware.** Every channel carries `value = A * raw + B`, stored in the
ESP32's NVS, solved from one or two known references:

```
cal low  ph 4.00      # probe in the 4.00 buffer, let it settle
cal high ph 7.00      # probe in the 7.00 buffer -> solves A and B
cal 1p   moisture 0   # offset-only trim, keeps the existing gain
cal                   # list every channel
```

**In the probe.** The sensor has its own offset and gain registers, which
persist in the hardware and follow it to any controller:

```
sensor                # read them all back
sensor offset ph -2
sensor factor n 1.15
sensor npk n 120      # write a lab-measured value into the N register
```

That last one matters: the manual is explicit that the built-in NPK figures
come from a rapid indirect method and carry real error. The intended workflow
is to measure properly and write the result in.

All of these work on the serial console (115200 baud) and over MQTT — publish
to `NPKcommand`, replies come back on `NPKreply` — so the probe can be
calibrated from a dashboard without a USB cable.

## A note on historical data

The original firmware divided every channel by ten. Per the manual,
conductivity and N/P/K are whole units, so **anything those four logged is a
factor of ten low.** Multiply by 10 to compare with what this firmware
publishes. Moisture, temperature and pH are unaffected.
