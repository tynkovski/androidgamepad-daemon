#!/usr/bin/env python3
"""Sends a sine-wave steering stream over UDP to the daemon."""
import argparse
import math
import socket
import struct
import time

MAGIC = b"WHL1"
PACKET_FMT = "<4sIfff"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=5555)
    ap.add_argument("--hz", type=float, default=100.0)
    ap.add_argument("--freq", type=float, default=0.5, help="sine frequency (Hz)")
    ap.add_argument("--amplitude", type=float, default=1.0)
    args = ap.parse_args()

    addr = (args.host, args.port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[test] sending sine {args.freq} Hz at {args.hz} Hz to {addr}", flush=True)

    dt = 1.0 / args.hz
    seq = 0
    t0 = time.monotonic()
    next_t = t0

    try:
        while True:
            t = time.monotonic() - t0
            val = args.amplitude * math.sin(2 * math.pi * args.freq * t)
            pkt = struct.pack(PACKET_FMT, MAGIC, seq & 0xFFFFFFFF, val, 0.0, 0.0)
            sock.sendto(pkt, addr)
            seq += 1
            next_t += dt
            sleep = next_t - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
    except KeyboardInterrupt:
        print("\n[test] stopped", flush=True)
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
