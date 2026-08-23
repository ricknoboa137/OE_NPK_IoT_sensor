# SoilNode firmware

ESP32 node for the **JXBS-3001-TR soil 7-in-1 probe** (moisture, temperature,
conductivity, pH, N, P, K) over RS-485 Modbus RTU, publishing JSON to MQTT with
a per-channel linear calibration held in NVS.

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

Manual section 2.1:

| Probe wire | Goes to |
|---|---|
| Brown | **12–24 V DC +** |
| Black | 0 V, common with the ESP32 ground |
| Yellow (grey on some batches) | RS-485 **A** |
| Blue | RS-485 **B** |

The probe will not run off the ESP32 3V3 rail — it needs its own 12 V supply.
Reversing A and B is the single most common reason for "no reply".

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
{"Humidity":34.6,"Temperature":21.4,"Conductivity":412,"PH":6.82,
 "Nitrogen":38,"Phosphorus":21,"Potassium":95,"ok":true}
```

`ok` is false when at least one register did not answer this cycle; the
affected channels then carry their last good value rather than a zero.

## Register map, and where the manual is wrong

From section 4.3 of the manual:

| Register | Quantity | Unit | Scale |
|---|---|---|---|
| `0x0006` | pH | 0.01 pH | ÷100 |
| `0x0012` | Soil moisture | 0.1 %RH | ÷10 |
| `0x0013` | Soil temperature | 0.1 °C | ÷10, **signed** |
| `0x0015` | Conductivity | 1 µS/cm | ÷1 |
| `0x001E` | Nitrogen | 1 mg/kg | ÷1 |
| `0x001F` | Phosphorus | 1 mg/kg | ÷1 |
| `0x0020` | Potassium | 1 mg/kg | ÷1 |
| `0x0100` | Device address | | read/write |
| `0x0101` | Baud rate | | read/write |

Temperature is the only signed value: section 4.4.1 reads `FF9B` back as
−10.1 °C.

**The map is sparse — it is not seven contiguous registers starting at
`0x0000`.** The original sketch sent `01 03 00 00 00 07` and sliced the reply
into seven values; on a probe that matches this manual, that block does not
hold the measurements at all. The firmware issues four transactions instead,
each one a frame the manual prints verbatim in section 4.4.

Two cautions, both found by checking the manual against itself:

1. **Several of the printed CRCs are wrong.** Recomputing CRC-16/MODBUS over
   the printed frames, the pH (`0x0006`), conductivity (`0x0015`) and potassium
   (`0x0020`) examples check out. The nitrogen and phosphorus examples have
   their CRCs *transposed* with each other, the three-register NPK read
   (§4.4.5) carries the CRC for `0x001F` rather than `0x001E`, and both
   moisture examples (§4.4.1, §4.4.2) carry CRCs computed for register
   `0x0002` rather than the `0x0012` the same sections name. The manual has
   other transcription errors of the same kind — §4.4.4 says "0047H = 308"
   where the frame it just printed reads `0134H`. Do not copy the printed
   CRCs; the firmware computes them.

2. **This family has variants.** Some clones really do answer on a contiguous
   block at `0x0000`, which is presumably where the original sketch's frame
   came from. If the datasheet profile returns nothing, run `scan` to see what
   your unit actually answers on, then set
   `NPK_REGISTER_PROFILE` to `NPK_PROFILE_LEGACY` in `NpkConfig.h` if the
   contiguous block is the live one.

Baud is auto-probed at boot across 4800, 9600 and 2400 — 4800 first because
that is what the original sketch used, though the datasheet says the factory
default is 9600. Set `NPK_BAUD_AUTODETECT` to 0 to pin it.

If a channel comes back with a plausible number at the wrong magnitude — pH
reading 0.68 instead of 6.8, say — that is a scale mismatch, and a two-point
calibration absorbs it into A without touching the code.

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
