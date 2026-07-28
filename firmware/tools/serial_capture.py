#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serial capture helper (K6-safe): open a UART, capture for N seconds, echo to
stdout and write to a log file. Forces UTF-8 so GBK-decoded boards don't crash.

Usage:
  python tools/serial_capture.py --port COM6 --baud 115200 --duration 45 \
      --out logs/campus_auth_serial.log
"""
import argparse
import io
import sys
import time

try:
    import serial
except ImportError:
    sys.stderr.write("pyserial not available\n")
    sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--duration", type=int, default=45)
    ap.add_argument("--out", default="serial.log")
    ap.add_argument("--timeout", type=float, default=0.5)
    args = ap.parse_args()

    # UTF-8 across the board (K6)
    out = io.open(args.out, "w", encoding="utf-8", newline="\n")
    sys.stdout.reconfigure(encoding="utf-8") if hasattr(sys.stdout, "reconfigure") else None

    ser = serial.Serial(port=args.port, baudrate=args.baud, timeout=args.timeout)
    # ESP8266 boot may need DTR/RTS toggled; leave default.
    end = time.time() + args.duration
    print(f"[capture] {args.port} {args.baud} for {args.duration}s -> {args.out}")
    try:
        while time.time() < end:
            raw = ser.readline()
            if not raw:
                continue
            try:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            except Exception:
                line = raw.decode("latin-1", errors="replace").rstrip("\r\n")
            ts = time.strftime("%H:%M:%S")
            print(f"{ts} {line}")
            out.write(line + "\n")
            out.flush()
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        out.close()
    print("[capture] done")


if __name__ == "__main__":
    main()
