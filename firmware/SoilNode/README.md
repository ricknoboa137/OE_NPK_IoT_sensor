# SoilNode firmware

ESP32 node for the **CWT soil sensor (NPK type)** five-pin probe — moisture,
temperature, conductivity, pH, nitrogen, phosphorus, potassium — over RS-485
Modbus RTU, publishing JSON to MQTT with a per-channel linear calibration
held in NVS.

## Files

| File | Responsibility |
|---|---|
| `SoilNode.ino` | setup/loop, sample scheduling, payload assembly |
| `NpkConfig.h` | every tunable: pins, baud, topics, intervals, register map |
| `NpkSensor.h/.cpp` | the channels, and the Modbus RTU master (read and write) |
| `NpkCal.h/.cpp` | A and B per channel, persisted in NVS |
| `NpkNet.h/.cpp` | WiFiManager provisioning, MQTT link, backoff |
| `NpkConsole.h/.cpp` | console shared by the serial port and MQTT |
| `NpkJson.h` | one macro so it builds against ArduinoJson 6 and 7 |

Every file and every type is prefixed `Npk`. That is deliberate — see
[Naming](#naming) below.

## Dependencies

Board: **ESP32 Dev Module** (Arduino-ESP32 core 2.x or 3.x; tested against
3.2.1). The library set is the same one the original sketch used.

| Library | Notes |
|---|---|
| [WiFiManager](https://github.com/tzapu/WiFiManager) | tzapu |
| [PubSubClient](https://github.com/knolleary/pubsubclient) | 2.8 or newer, for `setBufferSize` |
| [ArduinoJson](https://arduinojson.org/) | 6 or 7 |
| EspSoftwareSerial | ships with the ESP32 core |

`Preferences` and `WiFi` also ship with the core. `Preferences` is what holds
the calibration coefficients across a power cycle.

## Provisioning

On first boot with no stored WiFi credentials the node raises an access point
called **`NPK_Sensor_V2`**. Join it, and the captive portal asks for:

| Field | Notes |
|---|---|
| WiFi network and password | scanned from the air |
| MQTT broker | hostname or IP |
| MQTT port | 1883 by default |
| MQTT username | **leave empty if the broker does not require it** |
| MQTT password | leave empty if not required |

All five are written to NVS and reloaded at boot. When the username is empty
the node connects anonymously — PubSubClient then sends no CONNECT username
at all, which is what a Mosquitto with `allow_anonymous true` expects. Sending
an empty string instead makes some brokers refuse the connection.

The password box is served **blank** even when a password is stored, so the
stored one is never handed out over an open AP. Submitting it blank keeps the
existing password; to remove it, clear the username field, which switches the
node back to anonymous.

### Why the AP may not appear

`autoConnect()` only raises the AP when it **fails** to connect. If the board
already has WiFi credentials — including ones saved by a previous sketch, since
they live in the NVS partition and survive reflashing — it connects silently
and no portal appears. That is working as intended, not a fault.

Three ways to open the portal anyway:

- **Hold the BOOT button** during the first three seconds after power-up. The
  node prints a prompt and waits. Press it *after* the board starts, not while
  resetting: GPIO0 held low through reset puts the ESP32 into download mode
  instead. The pin and timing are `NPK_PORTAL_BTN_*` in `NpkConfig.h`.
- **`wifi portal`** on the serial console, which opens it without dropping the
  current WiFi connection.
- **`wifi reset`**, which erases the credentials and reboots, so the AP comes
  up on its own.

The broker settings can also be changed without the portal at all:

```
mqtt 192.168.0.153 1883
mqttauth myuser mypassword
mqttauth clear             # back to anonymous
```

Both are stored in NVS and take effect on the next reconnect. If the broker
rejects the connection, `status` decodes the reason rather than printing a bare
number — state 4 is a bad username or password, state 5 is not authorised.

## Calibration

Every channel carries two coefficients, and the node reports

```
value = A * raw + B
```

`raw` is the register value already divided by the datasheet scale factor, so
**A and B are in engineering units** — A is the span (gain) correction, B the
offset. Defaults are A = 1, B = 0, which reproduces the uncalibrated reading
exactly. Coefficients are written to NVS as soon as they are solved and survive
a power cycle.

Channel names: `moisture` `temperature` `conductivity` `ph` `nitrogen`
`phosphorus` `potassium` (aliases: `humidity` `temp` `ec` `n` `p` `k`).

### Two-point — the right method for pH and EC

Solves both coefficients from two known references:

```
A = (ref_high - ref_low) / (raw_high - raw_low)
B =  ref_low - A * raw_low
```

Put the probe in the low standard, let it settle, then:

```
cal low  ph 4.00
```

Rinse, move to the high standard, let it settle:

```
cal high ph 7.00
```

Each capture averages `NPK_CAL_SAMPLES` sweeps (8 by default) so a single noisy
frame cannot end up in the coefficients. The low point lives in RAM only —
rebooting between the two steps starts over. A solve is rejected if the two raw
readings are closer together than `NPK_CAL_MIN_SPAN`.

### One-point — offset trim

Keeps the existing gain and moves only the offset. Use it when the span is
believed good but there is a fixed error, e.g. a probe reading 2.4 %RH in dry
air:

```
cal 1p moisture 0
```

Running this after a two-point calibration re-trims the offset without
disturbing the fitted gain.

### Direct entry

```
cal set ph 0.94044 -0.06270
```

### Inspect and reset

```
cal                  list A and B for every channel
cal clear ph         one channel back to A=1, B=0
cal clear all
```

## Console

The same commands work on the serial console (115200 baud) and over MQTT.
Type `help` for the full list.

```
read                      take a reading, show raw / scaled / calibrated
status                    firmware, link and sensor state
scan [first] [last]       probe Modbus registers
mqtt <host> [port]        change broker, stored in NVS
mqttauth <user> [pass]    broker credentials, stored in NVS
mqttauth clear            connect anonymously
sensor                    read the probe's own calibration registers
sensor cal <n|p|k> low  <ref>    two-point solve, written into the probe
sensor cal <n|p|k> high <ref>
sensor offset <temp|hum|ec|ph> <raw>
sensor factor <n|p|k> <value>
sensor npk    <n|p|k> <mg/kg>
wifi portal               open the config portal now
wifi reset                forget WiFi and reboot
reboot
```

Over MQTT, publish either the plain text line or a JSON object to
`NPKcommand`; replies come back on `NPKreply`. A reply that does not fit the
buffer is published as far as it got, followed by an explicit truncation
notice — it is never silently cut. The serial copy is always complete.

```json
{"cmd":"cal_low",  "ch":"ph", "ref":4.00}
{"cmd":"cal_high", "ch":"ph", "ref":7.00}
{"cmd":"cal_1p",   "ch":"moisture", "ref":0}
{"cmd":"cal_set",  "ch":"ph", "a":0.94044, "b":-0.0627}
{"cmd":"cal_get"}
{"cmd":"cal_clear","ch":"all"}
{"cmd":"read"}
{"cmd":"status"}
{"cmd":"scan","first":0,"last":48}
{"cmd":"mqtt","host":"192.168.0.153","port":1883}
{"cmd":"mqttauth","user":"myuser","pass":"mypassword"}
{"cmd":"mqttauth"}
```

The `sensor` commands have no JSON form, but the plain-text line works over
MQTT too — publish `sensor npk n 120` to `NPKcommand` and the reply comes
back on `NPKreply` exactly as it would on the console.

## Topics

| Topic | Direction | Payload |
|---|---|---|
| `NPKdata` | publish | the reading, as JSON |
| `NPKstatus` | publish, retained | `online` / `offline` (LWT) / `sensor-unreachable` |
| `NPKcommand` | subscribe | console command, text or JSON |
| `NPKreply` | publish | console output |

The data payload keeps the key names the original sketch used, so an existing
Node-RED flow keeps working unchanged:

```json
{"Humidity":34.6,"Temperature":21.4,"Conductivity":0,"PH":6.8,
 "Nitrogen":38,"Phosphorus":21,"Potassium":95,"ok":true}
```

`ok` is false when at least one register did not answer this cycle; the
affected channels then carry their last good value rather than a zero.

## The sensor and its register map

The probe is a **CWT Soil sensor (NPK type)**, five-pin, from Shenzhen
ComWinTop. The authority is *NPK type (5Pin probe) manual V1.4*, included in
this folder. **All nine example frames in it CRC-check correctly** and every
worked example decodes to the value it claims — it is a reliable document.

Defaults: slave address `1`, RS485 `4800,n,8,1`.

### Measuring ranges (manual page 1)

| Quantity | Range | Accuracy | Response |
|---|---|---|---|
| Temperature | −40 … 80 °C | ±0.5 °C @ 25 °C | ≤15 s |
| Humidity | 0 – 100 %RH | ±3 % below 50 %, ±5 % above | ≤4 s |
| Conductivity | 0 – 20000 µS/cm | ±3 % to 10000, ±5 % above | ≤1 s |
| pH | 3 – 9 pH | ±0.3 pH | ≤10 s |
| N, P, K | 1 – 2999 mg/kg (mg/L) | resolution 1 mg/kg | <1 s |

Power DC 4.5–30 V (the wiring table says 5–30 V), max 0.5 W at 24 V, IP68,
2 m cable, 45 × 15 × 123 mm. Sensing volume is roughly a 5 cm sphere around
the pins.

> **The manual's own caveat on NPK:** "The measurement of NPK adopts the
> general rapid detection method, so there are certain errors, use with
> caution for planting reference." It is an indirect estimate derived from
> conductivity, not a chemical assay. See *Writing measured NPK values* below
> for the intended workaround.

### Wiring (manual page 2)

| Cable | Function |
|---|---|
| Brown | Power + (DC 5–30 V) |
| Black | Power − |
| Yellow **or green** | RS485 **A+** |
| Blue | RS485 **B−** |

The wide supply range means the board's 5 V rail is enough — no separate 12 V
supply. It will not run off 3V3. Grounds must be common with the ESP32, and
reversing A/B is the usual cause of "no reply".

### Registers (manual pages 3–4)

Measurements, function code `0x03`:

| Register | Content | Unit | Access |
|---|---|---|---|
| `0x0000` | Humidity | 0.1 %RH → **÷10** | read |
| `0x0001` | Temperature | 0.1 °C → **÷10**, signed | read |
| `0x0002` | Conductivity | 1 µS/cm → **÷1** | read |
| `0x0003` | pH | 0.1 → **÷10** | read |
| `0x0004` | Nitrogen | 1 mg/kg → **÷1** | read / **write** |
| `0x0005` | Phosphorus | 1 mg/kg → **÷1** | read / **write** |
| `0x0006` | Potassium | 1 mg/kg → **÷1** | read / **write** |
| `0x0007` | Salinity | 1 mg/L | read |
| `0x0008` | TDS | 1 mg/L | read |

The sensor's own calibration, written with function code `0x06`:

| Register | Content |
|---|---|
| `0x0022` | Conductivity factor, 0–100 = 0.0–10.0 %, default 0 |
| `0x0023` | Salinity factor, 0–100 = 0.00–1.00, default 55 |
| `0x0024` | TDS factor, 0–100 = 0.00–1.00, default 50 |
| `0x0050` | Temperature offset, 0.1 |
| `0x0051` | Humidity offset, 0.1 |
| `0x0052` | Conductivity offset, 1 |
| `0x0053` | pH offset, 1 |
| `0x04E8` / `0x04E9` / `0x04EA` | Nitrogen factor (IEEE-754 float, high word first) / offset |
| `0x04F2` / `0x04F3` / `0x04F4` | Phosphorus factor / offset |
| `0x04FC` / `0x04FD` / `0x04FE` | Potassium factor / offset |
| `0x07D0` | Slave ID, 1–254 |
| `0x07D1` | Baud rate, 0 = 2400, 1 = 4800, 2 = 9600 |

> The manual's prose says "read function code: 0x30, write function code:
> 0x60". Every worked example uses `0x03` and `0x06`, and those are what match
> the printed CRCs — `0x30`/`0x60` is a typo for the decimal function numbers
> 3 and 6.

### What this firmware reads

One transaction, byte for byte both the request the original sketch sent and
the manual's own combined-read example:

```
->  01 03 00 00 00 07 04 08
<-  01 03 0E 01D0 014C 002C 005A 0020 0058 0068 70 29

    0x01D0 = 464  ÷10  ->  46.4 %RH
    0x014C = 332  ÷10  ->  33.2 °C
    0x002C =  44  ÷1   ->  44 µS/cm
    0x005A =  90  ÷10  ->  9.0 pH
    0x0020 =  32  ÷1   ->  32 mg/kg N
    0x0058 =  88  ÷1   ->  88 mg/kg P
    0x0068 = 104  ÷1   ->  104 mg/kg K
```

Both CRCs verify and all seven values match the manual's text. Slots are
mapped in the original decoder's order, so previously logged data lines up:

| Slot | Register | Channel | Scale |
|---|---|---|---|
| 0 | `0x0000` | moisture | ÷10 |
| 1 | `0x0001` | temperature | ÷10, signed |
| 2 | `0x0002` | conductivity — published, always 0.0 here | ÷1 |
| 3 | `0x0003` | pH | ÷10 |
| 4 | `0x0004` | nitrogen | ÷1 |
| 5 | `0x0005` | phosphorus | ÷1 |
| 6 | `0x0006` | potassium | ÷1 |

Salinity and TDS at `0x0007`/`0x0008` are documented but not read; adding them
means extending `NPK_REG_COUNT` to 9 and adding two channels.

### Conductivity

Register `0x0002` sits in the middle of the block already being read, so it is
decoded and published like everything else.

**Expect a constant 0.0 from this unit.** The register answers with a valid
CRC, but the probe does not actually measure conductivity, so zero is the
correct reading rather than a fault or a comms failure. It is published anyway
so the payload keeps a stable shape for whatever consumes it, and so a unit
that *does* measure it needs no change at all.

Zero sits inside the 0–20000 µS/cm range, so the range check passes it and
`ok` stays true — a constant zero here is not treated as an error.

`NPK_ENABLE_CONDUCTIVITY` in `NpkConfig.h` drops it from the payload if a
constant zero is more noise than it is worth. That one define carries through
the enum, the channel table and the slot map.

Worth knowing separately: the original firmware also published conductivity.
The reason it never reached the database is that the Node-RED flow's `INSERT`
omits the column — a flow fix, not a firmware one.

### Scaling corrections against the original sketch

The original divided **every** channel by ten. Per this manual, conductivity
and N/P/K are whole units:

| Channel | Original | Correct | Effect |
|---|---|---|---|
| Humidity | ÷10 | ÷10 | unchanged |
| Temperature | ÷10 | ÷10 | unchanged |
| pH | ÷10 | ÷10 | unchanged |
| Conductivity | ÷10 | **÷1** | was 10× low |
| Nitrogen | ÷10 | **÷1** | was 10× low |
| Phosphorus | ÷10 | **÷1** | was 10× low |
| Potassium | ÷10 | **÷1** | was 10× low |

**Historical N/P/K data is a factor of ten low.** Anything logged by the
original firmware needs multiplying by 10 to sit on the same scale as what
this firmware now publishes. Moisture, temperature and pH are unaffected.

### Writing measured NPK values

Because the built-in NPK estimate is indirect, the manual's intended workflow
is to measure with proper instruments and write the result into the sensor, so
the monitoring system reads a real number:

```
sensor npk n 120        write 120 mg/kg into the nitrogen register
sensor npk p 45
sensor npk k 210
```

The probe reports that value until it next measures. There are also gain and
offset registers per nutrient:

```
sensor                        read every calibration register back
sensor factor n 1.15          nitrogen gain, IEEE-754 float over two registers
sensor offset temp -5         raw offset register, here -0.5 °C
```

### Recalculating the probe's A and B from standards

The probe ships with a gain and an offset already set per nutrient. Rather
than overwrite them blindly, `sensor cal` reads the existing pair, measures
against two standards, and composes a correction on top:

```
sensor cal n low  50      probe in the 50 mg/kg standard
sensor cal n high 200     probe in the 200 mg/kg standard
```

With the probe reporting `y = A·x + B` over some internal `x`, two standards
`r1`, `r2` giving reported `y1`, `y2`:

```
g  = (r2 - r1) / (y2 - y1)
A' = A · g
B' = r1 - g · (y1 - B)
```

`x` never appears, so the probe's internal scaling does not need to be known,
and the result is the same whatever the starting coefficients were. What *is*
assumed is that the probe applies factor then offset in that order — the
manual names both registers but never states the formula. So the write is
followed by a read-back and a fresh measurement against the high standard, and
the command says so if the result is further off than it should be.

Three things worth knowing:

- **A negative solved gain means the standards were swapped**, and the
  verification cannot detect it — the fit is self-consistent against whatever
  labels it was given, so it reads back perfectly while being backwards. The
  command warns explicitly when this happens.
- **The offset register is an integer**, so `B` is quantised to whole units.
- **The gain write is two registers.** If the first succeeds and the second
  fails, the probe is left half-updated; the command says so and the fix is to
  re-run it.

Only N, P and K have both a gain and an offset. Temperature, humidity,
conductivity and pH have **offset only** — no gain register — so a span
correction for those has to happen in the firmware layer with `cal`.

### The two layers

These live **in the probe** and persist there independently of this firmware.
They are a different thing from the `cal` commands, which correct readings
inside the ESP32 and are stored in its NVS. Either can do the job; the
sensor-side ones follow the probe if you move it to another controller, the
firmware-side ones do not touch the hardware and are easier to undo.

Slave ID and baud rate registers are deliberately **not** exposed as commands.
Getting either wrong loses communication until you find the device again by
scanning, and neither needs changing in normal use.

### Range checking

`NPK_RANGE_CHECK` tests every reading against the ranges in the table above.
Anything outside is marked out of range, excluded from the payload, and
reported by `read` with the raw register value and the limit it breached.

This exists because a wrong scale or slot mapping does **not** fail cleanly on
this hardware. The probe answers with a valid CRC at addresses it does not
implement, aliasing them onto the low block, so a bad map produces well-formed
nonsense rather than a timeout — 152.4 %RH and 4090 mg/kg with `ok:true`. The
CRC cannot catch that; only the physical limits can. Set it to 0 to disable.

`scan` prints every register that answers together with its ÷1, ÷10 and ÷100
interpretations, which is the quickest way to check a unit against known
conditions.

## Naming

Every file and type in this sketch is prefixed `Npk`, and it needs to stay
that way.

arduino-esp32 3.x declares `class NetworkManager` in
`libraries/Network/src/NetworkManager.h`, which `WiFi.h` pulls in
transitively. An earlier revision of this firmware had its own
`NetworkManager` class, and the two collided:

```
error: redefinition of 'class NetworkManager'
```

The prefix makes that whole class of clash impossible. Checked against the
3.2.1 tree: no file or type name in this sketch collides with anything the
core declares.

### If you rename a file in this sketch

Arduino leaves the old copy behind in its build folder and keeps compiling it
([arduino-cli#1699](https://github.com/arduino/arduino-cli/issues/1699)), which
produces errors pointing at a file that no longer exists on disk. Clear the
cache after any rename:

```
%LOCALAPPDATA%\arduino\sketches
```

Deleting that folder is safe; it is rebuilt on the next compile.

## Changes from the original sketch

Behavioural fixes, beyond the reorganisation:

- **Scaling.** The original divided every channel by ten. Conductivity and
  N, P and K are whole units per the manual, so those four were reported a
  factor of ten low. Moisture, temperature and pH were correct.
- **Register map.** Unchanged — the original's single read of seven registers
  from `0x0000` is exactly what the manual specifies, and is kept.
- **Reply framing.** The old `GetValues()` read whatever bytes happened to be
  in the buffer immediately after writing the request, with no wait, no length
  check and no CRC check, then indexed `values[16]` in an array declared
  `values[11]`. That is a buffer overrun on every successful read.
- **A broker outage no longer wipes the WiFi credentials.** The old
  `reconnect()` called `wm.resetSettings()` after five failed MQTT attempts, so
  restarting the broker could strand the node in AP mode.
- **The portal's MQTT fields now take effect.** `setServer()` was previously
  called with the compile-time defaults before the portal values were read, and
  the values were never persisted. They are now stored in NVS and reloaded at
  boot.
- **Failed reads are not published as zeros.** Zero is a legitimate reading for
  every one of these channels.
- **Non-blocking.** Reconnection uses exponential backoff instead of a
  blocking retry loop, so sampling and the console keep running while the
  broker is down.
- The MQTT callback no longer writes an unterminated payload into a fixed
  20-byte buffer.
- Unique MQTT client ID derived from the MAC, so two nodes no longer evict each
  other from the broker.

## Status

Verified:

- All nine example frames in the manual CRC-check correctly, and every
  documented value decodes as stated, using this firmware's CRC routine.
- The calibration algebra (one-point, two-point, guards, gain preservation)
  was unit-tested separately against 18 cases.
- Checked statically for unresolved includes, declared-but-undefined methods,
  bracket balance with literals stripped, enum/table/slot-map agreement under
  both settings of `NPK_ENABLE_CONDUCTIVITY`, and name collisions against the
  arduino-esp32 3.2.1 tree.

Not verified: **the register-write path has never run against hardware.** The
`sensor offset`, `sensor factor` and `sensor npk` commands are built from the
manual's worked examples and their frames are CRC-correct, but nothing has
confirmed the probe accepts them. Read `sensor` first to see the current
values before writing anything, and note them down.

The reading path was compiled and run; the writing path was not, and there is
no Arduino toolchain on the machine this was written on.
