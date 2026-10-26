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
| [`flows.json`](flows.json) | the Node-RED flow — MQTT input, database logging, dashboard, calibration page |
| [`database/`](database/) | the database: its schema, the logged readings, and a script that builds the SQLite file |
| [`tools/paper/`](tools/paper/) | the scripts that reproduce the figures and numbers of the manuscript |
| [`tools/`](tools/) | utilities used during development (register scans, flow editing, checks) |

The probe's manual is in the firmware folder. Full documentation of the
firmware — dependencies, provisioning, console, register map and the
calibration procedure — is in
**[firmware/SoilNode/README.md](firmware/SoilNode/README.md)**.

## Connections

The pin numbers are those set in
[`firmware/SoilNode/NpkConfig.h`](firmware/SoilNode/NpkConfig.h); change them
there if the board is wired differently.

| ESP32 | RS-485 transceiver (MAX485 module) | Note |
|---|---|---|
| GPIO 18 (RX) | RO | data from the probe |
| GPIO 19 (TX) | DI | data to the probe |
| GPIO 4 | DE and RE, tied together | direction control |
| GND | GND | common ground |

| Probe cable | Connects to |
|---|---|
| Brown | supply + (5–30 V DC according to the manual; the prototype uses an MT3608 step-up module set to 9 V) |
| Black | supply − and common ground |
| Yellow or green | A on the transceiver (RS-485 A+) |
| Blue | B on the transceiver (RS-485 B−) |

GPIO 2 drives the on-board LED. Holding GPIO 0 (the BOOT button) low just after
the board starts opens the configuration portal. The grounds of the ESP32, the
transceiver and the probe supply must be common; swapping A and B is the usual
cause of a probe that does not answer. Supply the transceiver module as its own
datasheet specifies.

## Instructions

1. **Firmware.** Open `firmware/SoilNode/SoilNode.ino` in the Arduino IDE with
   the ESP32 board package, install the libraries listed in the firmware README
   (WiFiManager, PubSubClient 2.8 or newer, ArduinoJson 6 or 7), and upload it.
2. **MQTT broker.** Run any MQTT broker reachable from the node on port 1883,
   for example Mosquitto on the computer that will run Node-RED.
3. **Provisioning.** On first start the node opens the access point
   `NPK_Sensor_V2`. Connect to it, choose the WiFi network and enter the address
   of the broker. The node then publishes a reading every 5 s on the topic
   `NPKdata`.
4. **Node-RED.** Install Node-RED and, from *Manage palette*, the packages
   `node-red-dashboard` and `node-red-node-sqlite`. Import `flows.json`
   (*Menu → Import*), then edit two configuration nodes, which hold values of
   the development computer:
   - the MQTT broker node: set the address of your broker;
   - the SQLite database node: set the path where the database file is to be kept.

   Deploy. The dashboard is served at `http://<computer>:1880/ui`, with the
   pages *Lectures*, *Charts* and *Calibration*.
5. **Database.** Nothing has to be prepared: the flow creates the tables if they
   do not exist and stores every reading as it arrives. See the next section to
   start from the recorded data instead.

## Database

The flow logs to a SQLite file with two tables, described in
[`database/schema.sql`](database/schema.sql): `NPKv1`, one row per reading, and
`probe_cal_backup`, the calibration backups saved from the dashboard.

[`database/sensor_log.csv.gz`](database/sensor_log.csv.gz) holds the readings
recorded from 12 January to 26 October 2026 (210,251 rows, times in UTC); the
manuscript uses those up to 9 September. To obtain the SQLite file from it:

```
python database/build_database.py
```

This writes `DB_01.db` in the repository root, which can be opened with any
SQLite tool or given to the flow as its database. The live database itself is
not versioned, because it changes with every reading. Readings logged before
23 August 2026 have N, P and K a factor of ten low (see the note at the end).

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
sensor                    # read them all back
sensor cal n low  50      # two-point against standards, solved and
sensor cal n high 200     #   written into the probe itself
sensor npk n 120          # or write a lab-measured value directly
```

That last one matters: the manual is explicit that the built-in NPK figures
come from a rapid indirect method and carry real error. The intended workflow
is to measure properly and write the result in.

All of these work on the serial console (115200 baud) and over MQTT — publish
to `NPKcommand`, replies come back on `NPKreply` — so the probe can be
calibrated from a dashboard without a USB cable.

## A note on historical data

Bug corrected from the original version where N, p, K values where divided by a factor of 10 i.e. (/10)
