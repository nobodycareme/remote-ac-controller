#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bidirectional serial helper (K6-safe): open a UART, capture output to a log
file, and send CLI commands on a trigger / schedule. Forces UTF-8 so GBK-
decoded boards don't crash.

Usage:
  python tools/serial_interact.py --port COM6 --baud 115200 --duration 50 \
      --out logs/nodemcuv2_serial.log \
      --trigger "APP_BOOT_OK" --send "wifi connect" --send-delay 1.0 \
      --send2 "net check" --send2-delay 25.0
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
    ap.add_argument("--duration", type=int, default=50)
    ap.add_argument("--out", default="serial.log")
    ap.add_argument("--trigger", default="APP_BOOT_OK")
    ap.add_argument("--send", default="")
    ap.add_argument("--send-delay", type=float, default=1.0)
    ap.add_argument("--send2", default="")
    ap.add_argument("--send2-delay", type=float, default=25.0)
    ap.add_argument("--fallback", type=float, default=8.0,
                    help="send cmd1 after this many seconds if trigger never seen")
    args = ap.parse_args()

    out = io.open(args.out, "w", encoding="utf-8", newline="\n")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ser = serial.Serial(port=args.port, baudrate=args.baud, timeout=0.5)
    t0 = time.time()
    t_trigger = None
    sent1 = False
    sent2 = False
    t_sent1 = None

    print(f"[interact] open {args.port} {args.baud} for {args.duration}s -> {args.out}")
    try:
        while time.time() - t0 < args.duration:
            raw = ser.readline()
            if raw:
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                except Exception:
                    line = raw.decode("latin-1", errors="replace").rstrip("\r\n")
                ts = time.strftime("%H:%M:%S")
                print(f"{ts} {line}")
                out.write(line + "\n")
                out.flush()
                if t_trigger is None and args.trigger and args.trigger in line:
                    t_trigger = time.time() - t0
                    print(f"[interact] trigger '{args.trigger}' @ {t_trigger:.1f}s; "
                          f"cmd1 in {args.send_delay}s")

            elapsed = time.time() - t0

            # schedule command 1
            if args.send and not sent1:
                t_send1 = (t_trigger + args.send_delay) if t_trigger is not None \
                    else args.fallback
                if elapsed >= t_send1:
                    ser.write((args.send + "\r\n").encode("utf-8"))
                    ser.flush()
                    sent1 = True
                    t_sent1 = elapsed
                    print(f"[interact] >> sent: {args.send}  (@{elapsed:.1f}s)")

            # schedule command 2
            if args.send2 and not sent2 and sent1 and (elapsed - t_sent1 >= args.send2_delay):
                ser.write((args.send2 + "\r\n").encode("utf-8"))
                ser.flush()
                sent2 = True
                print(f"[interact] >> sent: {args.send2}  (@{elapsed:.1f}s)")
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
        out.close()
    print("[interact] done")


if __name__ == "__main__":
    main()
