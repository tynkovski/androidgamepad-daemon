#!/usr/bin/env python3
"""
wireless_wheel_daemon.py v3 — UDP → uinput wireless wheel + pedals + buttons
for BeamNG.drive (Linux native).

Two UDP sockets:
  5555 — continuous control stream, 24-byte packets, 100 Hz, little-endian:
          0  4  bytes   magic 'WHL2'
          4  4  uint32  seq
          8  4  float32 steering [-1..+1]
          12 4  float32 throttle [0..1]
          16 4  float32 brake    [0..1]
          20 4  float32 clutch   [0..1]  (reserved, currently unused)
  5556 — one-shot button events, 1-byte payload:
          'u' → shift up    (BTN_TR)
          'd' → shift down  (BTN_TL)
          'n' → neutral     (BTN_SELECT)
          'h' → handbrake   (BTN_EAST)

Axes exposed on the virtual gamepad:
  ABS_X  steering  [-32767..32767]    (not inverted)
  ABS_Y  throttle  [0..32767]         (inverted: PEDAL_MAX - t)
  ABS_Z  brake     [0..32767]         (not inverted)
  ABS_RX right stick, always 0        (so camera doesn't move)
  ABS_RY right stick, always 0
  ABS_RZ reserved for clutch, always 0
"""
import argparse
import signal
import socket
import struct
import sys
import time

from evdev import UInput, AbsInfo, ecodes as e

MAGIC = b"WHL2"
PACKET_FMT = "<4sIffff"
PACKET_SIZE = struct.calcsize(PACKET_FMT)  # 24
STEER_MAX = 32767
PEDAL_MAX = 32767
WATCHDOG_TIMEOUT = 0.3
EMIT_INTERVAL = 0.01
DECAY_PER_TICK = 0.85
CENTER_EPSILON = 0.005
BUTTON_HOLD_MS = 50


def create_uinput() -> UInput:
    return UInput(
        {
            e.EV_ABS: [
                (e.ABS_X,  AbsInfo(0, -STEER_MAX, STEER_MAX, 0, 0, 0)),  # steering
                (e.ABS_Y,  AbsInfo(0, 0, PEDAL_MAX, 0, 0, 0)),           # throttle
                (e.ABS_Z,  AbsInfo(0, 0, PEDAL_MAX, 0, 0, 0)),           # brake
                (e.ABS_RX, AbsInfo(0, -STEER_MAX, STEER_MAX, 0, 0, 0)),  # right stick
                (e.ABS_RY, AbsInfo(0, -STEER_MAX, STEER_MAX, 0, 0, 0)),  # right stick
                (e.ABS_RZ, AbsInfo(0, 0, PEDAL_MAX, 0, 0, 0)),           # clutch (reserved)
            ],
            e.EV_KEY: [
                e.BTN_SOUTH,
                e.BTN_TRIGGER,
                e.BTN_TR,       # gear up
                e.BTN_TL,       # gear down
                e.BTN_SELECT,   # neutral
                e.BTN_EAST,     # handbrake
            ],
        },
        name="Android Wireless Wheel",
        version=1,
        bustype=e.BUS_USB,
    )


def emit(ui: UInput, steering, throttle, brake, clutch) -> None:
    s = int(max(-1.0, min(1.0, steering)) * STEER_MAX)
    t = int(max(0.0, min(1.0, throttle)) * PEDAL_MAX)
    b = int(max(0.0, min(1.0, brake)) * PEDAL_MAX)
    ui.write(e.EV_ABS, e.ABS_X,  s)                    # steering
    ui.write(e.EV_ABS, e.ABS_Y,  PEDAL_MAX - t)        # throttle (inverted)
    ui.write(e.EV_ABS, e.ABS_Z,  b)                    # brake
    ui.write(e.EV_ABS, e.ABS_RX, 0)                    # right stick = 0
    ui.write(e.EV_ABS, e.ABS_RY, 0)                    # right stick = 0
    ui.write(e.EV_ABS, e.ABS_RZ, 0)                    # clutch reserved
    ui.syn()


def press_button(ui: UInput, code: int, hold_ms: int = BUTTON_HOLD_MS) -> None:
    ui.write(e.EV_KEY, code, 1)
    ui.syn()
    time.sleep(hold_ms / 1000.0)
    ui.write(e.EV_KEY, code, 0)
    ui.syn()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=5555,
                    help="continuous stream UDP port (default 5555)")
    ap.add_argument("--evt-port", type=int, default=5556,
                    help="button events UDP port (default 5556)")
    ap.add_argument("--invert-steering", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    # control stream socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.bind, args.port))
    sock.setblocking(False)
    print(f"[daemon] UDP on {args.bind}:{args.port}", flush=True)

    # button events socket
    sock_evt = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock_evt.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock_evt.bind((args.bind, args.evt_port))
    sock_evt.setblocking(False)
    print(f"[daemon] event UDP on {args.bind}:{args.evt_port}", flush=True)

    ui = create_uinput()
    print("[daemon] uinput 'Android Wireless Wheel' created", flush=True)

    running = True
    def _stop(*_):
        nonlocal running
        running = False
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    last_recv = 0.0
    target = [0.0, 0.0, 0.0, 0.0]  # steer, throttle, brake, clutch
    watchdog_fired = False
    last_emit = time.monotonic()
    packets_total = 0
    last_status = time.monotonic()
    peer = None

    try:
        while running:
            now = time.monotonic()

            # --- control stream ---
            try:
                while True:
                    data, addr = sock.recvfrom(1024)
                    if len(data) != PACKET_SIZE:
                        if args.verbose:
                            print(f"[daemon] bad size {len(data)} from {addr}", flush=True)
                        continue
                    magic, seq, st, th, br, cl = struct.unpack(PACKET_FMT, data)
                    if magic != MAGIC:
                        if args.verbose:
                            print(f"[daemon] bad magic {magic!r} from {addr}", flush=True)
                        continue
                    last_recv = now
                    packets_total += 1
                    peer = addr
                    if args.invert_steering:
                        st = -st
                    target = [st, th, br, cl]
                    watchdog_fired = False
            except BlockingIOError:
                pass

            # --- button events ---
            try:
                while True:
                    data, addr = sock_evt.recvfrom(64)
                    if len(data) == 1:
                        cmd = data
                        if cmd == b'u':
                            press_button(ui, e.BTN_TR)
                            if args.verbose:
                                print(f"[daemon] gear UP from {addr}", flush=True)
                        elif cmd == b'd':
                            press_button(ui, e.BTN_TL)
                            if args.verbose:
                                print(f"[daemon] gear DOWN from {addr}", flush=True)
                        elif cmd == b'n':
                            press_button(ui, e.BTN_SELECT)
                            if args.verbose:
                                print(f"[daemon] gear NEUTRAL from {addr}", flush=True)
                        elif cmd == b'h':
                            press_button(ui, e.BTN_EAST)
                            if args.verbose:
                                print(f"[daemon] handbrake from {addr}", flush=True)
                        elif args.verbose:
                            print(f"[daemon] unknown event {data!r} from {addr}", flush=True)
            except BlockingIOError:
                pass

            # --- watchdog ---
            if last_recv > 0 and (now - last_recv) > WATCHDOG_TIMEOUT and not watchdog_fired:
                print("[daemon] watchdog: centering", flush=True)
                watchdog_fired = True

            # --- emit at ~100 Hz ---
            if now - last_emit >= EMIT_INTERVAL:
                if watchdog_fired:
                    target = [x * DECAY_PER_TICK for x in target]
                    target = [0.0 if abs(x) < CENTER_EPSILON else x for x in target]
                emit(ui, *target)
                last_emit = now

            # --- periodic status ---
            if args.verbose and now - last_status >= 5.0:
                print(f"[daemon] pkts={packets_total} peer={peer} "
                      f"steer={target[0]:+.2f} th={target[1]:.2f} "
                      f"br={target[2]:.2f} cl={target[3]:.2f}", flush=True)
                last_status = now

            time.sleep(0.001)
    finally:
        try:
            emit(ui, 0, 0, 0, 0)
        except Exception:
            pass
        ui.close()
        sock.close()
        sock_evt.close()
        print("[daemon] stopped", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
