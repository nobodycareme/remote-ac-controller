# capture_serial.py
# Timed serial log capture. Prints every line to stdout AND appends to --out.
# Uses pyserial (ships with the PlatformIO Core venv). UTF-8 safe.
# Usage:
#   python capture_serial.py --port COM6 --baud 115200 --duration 26 --out logs\hardware_integration\dht_serial.log
import argparse
import io
import sys
import time

try:
    import serial
except ImportError:
    print("pyserial not available in this Python")
    sys.exit(2)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--duration", type=float, default=20.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--probe", action="store_true",
                    help="Only test if the port can be opened; exit 0 ok, 2 busy.")
    args = ap.parse_args()

    if args.probe:
        try:
            s = serial.Serial(args.port, args.baud, timeout=1.0)
            s.close()
            print("PROBE_OK")
            return 0
        except Exception as e:  # noqa
            print("PROBE_BUSY: %s" % e)
            return 2

    try:
        s = serial.Serial(args.port, args.baud, timeout=0.5)
    except Exception as e:  # noqa
        print("SERIAL_OPEN_FAILED: %s" % e)
        return 2

    out_f = None
    if args.out:
        out_f = io.open(args.out, "a", encoding="utf-8", errors="replace")

    try:
        end = time.time() + args.duration
        while time.time() < end:
            try:
                raw = s.readline()
                if not raw:
                    continue
                line = raw.decode(errors="replace").rstrip("\r\n")
            except Exception:  # noqa
                break
            if line == "":
                continue
            print(line)
            sys.stdout.flush()
            if out_f:
                out_f.write(line + "\n")
                out_f.flush()
    finally:
        s.close()
        if out_f:
            out_f.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
