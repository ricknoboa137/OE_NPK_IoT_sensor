# SoilNode firmware

ESP32 node for the **VMS-3001-TR soil probe** (moisture, temperature, pH)
over RS-485 Modbus RTU, publishing JSON to MQTT with a per-channel linear
calibration held in NVS.

## Files

| File | Responsibility |
|---|---|
| `SoilNode.ino` | setup/loop, sample scheduling, payload assembly |
| `NpkConfig.h` | every tunable: pins, baud, topics, intervals, register profile |
| `NpkSensor.h/.cpp` | the seven channels, and the Modbus RTU master |
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

## Wiring

Manual section 2.2.1:

| Probe wire | Goes to |
|---|---|
| Brown | **4.5–30 V DC +** |
| Black | 0 V, common with the ESP32 ground |
| Yellow | RS-485 **A** |
| Blue | RS-485 **B** |

Wide supply range, so the board's 5 V rail is enough — this probe does not
need a separate 12 V supply. Maximum draw is 0.5 W at 24 V; it will be well
under that at 5 V. It will *not* run off 3V3.

Reversing A and B is the single most common reason for "no reply". Grounds
must be common between the probe supply and the ESP32.

Note the probe needs up to **5 minutes to stabilise** after power-up
(manual section 1.3, 稳定时间 ≤5min), and conductivity only reflects the soil
properly once volumetric moisture is above roughly 20 % — dry soil reads low
regardless of its actual salt content.

| ESP32 | Transceiver (MAX485 / similar) |
|---|---|
| GPIO18 | RO |
| GPIO19 | DI |
| GPIO4 | DE and RE, tied together |

Pins are set in `NpkConfig.h`. `NPK_USE_SOFTWARE_SERIAL` defaults to 1, matching
the original sketch; set it to 0 to use hardware UART1 on the same pins, which
is more robust under WiFi load because a bit-banged port can drop bytes when
the radio takes an interrupt.

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

Channel names: `moisture` `temperature` `ph` `nitrogen` `phosphorus`
`potassium` (aliases: `humidity` `temp` `n` `p` `k`).

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
wifi portal               open the config portal now
wifi reset                forget WiFi and reboot
reboot
```

Over MQTT, publish either the plain text line or a JSON object to
`NPKcommand`; replies come back on `NPKreply`.

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
{"Humidity":34.6,"Temperature":21.4,"PH":6.8,
 "Nitrogen":3.8,"Phosphorus":2.1,"Potassium":9.5,"ok":true}
```

`ok` is false when at least one register did not answer this cycle; the
affected channels then carry their last good value rather than a zero.

## The sensor and its register map

The probe is a **VMS-3001-TR-\*-N01**, 威盟士 (Weimengshi) five-pin soil
transmitter. Its own manual — *五插针土壤四参数传感器（485型）*, Ver 2.0 — is the
authority here, and unlike the JXBS manual this project started from, it is
internally consistent: both example CRCs verify and every worked example
decodes to the value it claims.

It is a **four-parameter** probe. Section 1.5 lists the whole model line:

| Suffix | Measures |
|---|---|
| `THPH` | temperature, moisture, pH |
| `ECPH` | conductivity, pH |
| `ECTHPH` | conductivity, temperature, moisture, pH |

### Registers (manual section 5.3)

| Register | Content | Access | Scaling |
|---|---|---|---|
| `0x0000` | Moisture | read | value ×10 → **÷10** for % |
| `0x0001` | Temperature | read | value ×10 → **÷10** for °C, **signed** |
| `0x0002` | Conductivity | read | **not scaled**, whole µS/cm |
| `0x0003` | pH | read | value ×10 → **÷10** |
| `0x0007` | Salinity | read | "for reference only" |
| `0x0008` | TDS | read | "for reference only" |
| `0x0022` | EC temperature coefficient | read/write | 0–100 = 0.0–10.0 %, default 0 |
| `0x0023` | Salinity coefficient | read/write | 0–100 = 0.00–1.00, default 55 |
| `0x0024` | TDS coefficient | read/write | 0–100 = 0.00–1.00, default 50 |
| `0x0050` | Temperature calibration | read/write | integer ×10 |
| `0x0051` | Moisture calibration | read/write | integer ×10 |
| `0x0052` | Conductivity calibration | read/write | integer |
| `0x0053` | pH calibration | read/write | integer |
| `0x07D0` | Device address | read/write | 1–254, factory default 1 |
| `0x07D1` | Baud rate | read/write | 0 = 2400, 1 = 4800, 2 = 9600 |

Serial defaults: 4800 baud, 8N1, no parity, slave address `0x01`.

The manual's own worked example (section 5.4), which the firmware's scaling is
checked against:

```
->  01 03 00 00 00 04 44 09
<-  01 03 08 02 92 FF 9B 03 E8 00 38 57 B6

    0x0292 =  658  /10  ->  65.8 %RH
    0xFF9B = -101  /10  -> -10.1 °C     (two's complement below zero)
    0x03E8 = 1000  /1   ->  1000 µS/cm
    0x0038 =   56  /10  ->  5.6 pH
```

Both CRCs recompute correctly, and all four values match the manual's text.

### What this firmware reads

One transaction, byte for byte the request the original sketch sent:

```
01 03 00 00 00 07 04 08      (seven registers from 0x0000, CRC verified)
```

and the reply is sliced in the original decoder's slot order, so previously
logged data stays comparable:

| Slot | Register | Mapped to | Scale |
|---|---|---|---|
| 0 | `0x0000` | moisture | ÷10 |
| 1 | `0x0001` | temperature | ÷10, signed |
| 2 | `0x0002` | *discarded* — this unit does not return conductivity | — |
| 3 | `0x0003` | pH | ÷10 |
| 4 | `0x0004` | nitrogen | ÷10 |
| 5 | `0x0005` | phosphorus | ÷10 |
| 6 | `0x0006` | potassium | ÷10 |

To restore conductivity: add `NPK_CONDUCTIVITY` to the enum in `NpkSensor.h`,
add a row to `NPK_CHANNELS`, and replace the `-1` in the read op with it.
Note the scale is **÷1**, not ÷10 — the original sketch divided it by ten,
which would have read 1000 µS/cm as 100.

### N, P and K are not real on this sensor

There are no nitrogen, phosphorus or potassium registers in this manual, and
no NPK variant in the model line. Slots 4, 5 and 6 are undocumented. They are
kept because the original decoder used them and the logged dataset carries
them, but **whatever those registers hold, it is not soil NPK.** In the
83,883 rows logged by the original firmware they sit nearly static — N ≈ 2.0,
P ≈ 9.3, K ≈ 8.5 for hours while moisture and temperature move — which is what
you would expect from something that is not a live measurement.

Measuring actual NPK needs a probe that advertises it, such as the JXBS-3001
seven-in-one. If you would rather have the two channels this sensor genuinely
does provide, `0x0007` (salinity) and `0x0008` (TDS) are documented and only
need the read extended to nine registers.

### Range checking

`NPK_RANGE_CHECK` tests every reading against the physical limits in manual
section 1.3 — 0–100 %RH, −40…80 °C, 3–9 pH (widened to 0–14 so a badly
calibrated probe still reports). Anything outside is marked out of range,
excluded from the payload, and reported by `read` with the raw register value
and the limit it breached.

This exists because a wrong slot mapping does **not** fail cleanly on this
hardware. The probe answers with a valid CRC at addresses it does not
implement, aliasing them onto the low block, so the output is well-formed
nonsense rather than a timeout — 152.4 %RH and 4090 mg/kg with `ok:true`. The
CRC cannot catch that; only the physical limits can. Set it to 0 to disable.

If a channel comes back plausible but at the wrong magnitude, that is a scale
mismatch and needs no code change — a two-point calibration absorbs it into
`A`. Use `scan` to see what every register actually returns, with its ÷1, ÷10
and ÷100 interpretations side by side.

### On-sensor calibration

Separately from this firmware's `A`/`B` correction, the probe has its own
calibration registers at `0x0050`–`0x0053` (offsets, written with function
0x06). Those change what the sensor reports; the firmware's coefficients
change how its output is interpreted. The firmware does not write them today —
say the word if you want commands for it.

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

- **Register map.** As above; the old contiguous read at `0x0000` did not match
  this manual.
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

The calibration algebra and the Modbus CRC were verified against the
datasheet's own example frames, and the sketch was checked statically for
unresolved includes, declared-but-undefined methods and name collisions
against the 3.2.1 core. **It has not been compiled or run on hardware** —
there is no Arduino toolchain on the machine it was written on.
