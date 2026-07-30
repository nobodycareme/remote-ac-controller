# serial_collect.py
# Serial log collector using pyserial (ships with PlatformIO Core venv).
# Modes:
#   --probe                : just try to open the port; exit 0 = ok, 2 = busy/denied
#   (default)              : capture for --duration seconds, search for --markers
#                           exit 0 = all markers found, 1 = not all found, 2 = open failed
import argparse
import sys
import time

try:
    import serial
except ImportError:
    print("pyserial not available in this Python")
    sys.exit(2)


# Force UTF-8 I/O so that replacement chars ('\ufffd') produced by
# decode(errors="replace") do not crash print() under the Windows console
# (gbk) codepage. See review/known-issues.md K6.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa
    pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True)
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--duration", type=float, default=12.0)
    ap.add_argument(
        "--markers",
        nargs="*",
        default=["ESP8266_SELF_TEST_START", "ESP8266_SELF_TEST_OK"],
    )
    ap.add_argument(
        "--probe",
        action="store_true",
        help="Only test if the port can be opened; exit 0 ok, 2 busy.",
    )
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

    found = set()
    try:
        end = time.time() + args.duration
        while time.time() < end:
            try:
                line = s.readline().decode(errors="replace").rstrip("\r\n")
            except Exception:  # noqa
                break
            if line:
                print(line)
                sys.stdout.flush()
            for m in args.markers:
                if m in line:
                    found.add(m)
            if all(x in found for x in args.markers):
                break
    finally:
        s.close()
    print("FOUND_MARKERS: %s" % ",".join(sorted(found)))
    sys.stdout.flush()
    return 0 if all(x in found for x in args.markers) else 1


if __name__ == "__main__":
    sys.exit(main())
