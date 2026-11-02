# androidjoystick-daemon

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform: Linux](https://img.shields.io/badge/platform-Linux-informational)
![Python 3](https://img.shields.io/badge/python-3-blue)

Android phone → wireless steering wheel, pedals, and gear/handbrake buttons
for **BeamNG.drive** (Linux native) over local Wi-Fi.

Phone sends control data via UDP at 100 Hz. A Python daemon on the PC receives
it and drives a virtual gamepad through `/dev/uinput`. BeamNG sees it as a
regular controller. No Bluetooth, no kernel modules, no extra drivers.

## Install

```bash
git clone <repo> && cd androidjoystick-daemon
./install.sh
```
## Companion Android app

The Android client that implements the protocol below (touch wheel + pedals + gear buttons) lives here:  
**https://github.com/tynkovski/MyJoystick**

## Why

Wanted to play BeamNG with my phone as a physical wheel. Gyroscope turned out
unusable (noisy, drifting), so I switched to touch: a half-sunk wheel you drag
with your thumb, plus two diagonal pedals. This repo is the PC-side daemon.
The Android app is a separate project — it just implements the protocol below.

## Features

- Virtual gamepad (`Android Wireless Wheel`) via uinput, picked up by SDL/BeamNG.
- Steering (`ABS_X`), throttle (`ABS_Y`), brake (`ABS_Z`) axes.
- Momentary buttons: shift up, shift down, neutral, handbrake.
- Watchdog: if the stream stops for 0.3 s, all axes return to zero.

## Protocol

UDP, little-endian.

**Control stream — port 5555, 24 bytes, 100 Hz**

| Offset | Size | Type    | Field    | Range |
|---|---|---|---|---|
| 0  | 4 | bytes   | magic    | `"WHL2"` |
| 4  | 4 | uint32  | seq      | counter |
| 8  | 4 | float32 | steering | −1.0 .. +1.0 |
| 12 | 4 | float32 | throttle | 0.0 .. 1.0 |
| 16 | 4 | float32 | brake    | 0.0 .. 1.0 |
| 20 | 4 | float32 | clutch   | 0.0 .. 1.0 (reserved) |

**Button events — port 5556, 1 byte**

| Byte | Action     |
|---|---|
| `'u'` | shift up   |
| `'d'` | shift down |
| `'n'` | neutral    |
| `'h'` | handbrake  |

## Axis mapping

| Axis     | Function      | Range           |
|----------|---------------|-----------------|
| `ABS_X`  | steering      | −32767..+32767  |
| `ABS_Y`  | throttle      | 0..32767 (inv.) |
| `ABS_Z`  | brake         | 0..32767        |
| `ABS_RX` | right stick   | always 0        |
| `ABS_RY` | right stick   | always 0        |
| `ABS_RZ` | clutch (res.) | always 0        |

## BeamNG setup

Add to Steam launch options:

```
SDL_JOYSTICK_DEVICE=/dev/input/js0 %command%
```

Then bind in `Options → Controls`.

## Run

Requires `python3-evdev`, `uinput` access (user in `input` group), and ports
5555/5556 open in the firewall.

```bash
python3 wireless_wheel_daemon.py --verbose
```

CLI flags: `--bind`, `--port`, `--evt-port`, `--invert-steering`, `--verbose`.

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Released under the **MIT License** — free to use, modify, and distribute,
including commercially, provided the copyright notice is preserved.

| | |
|---|---|
| **License** | MIT |
| **Copyright** | © 2026 tynkovski |
| **Full text** | [LICENSE](LICENSE) |
