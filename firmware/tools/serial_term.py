# serial_term.py
# Send an optional command to the MCU, then capture serial output for a duration.
# UTF-8 safe. Used for DHT11 self-test and IR learn/send phases.
# Usage:
#   python serial_term.py --port COM6 --baud 115200 --duration 30 \
#       --send "dht test" --send-delay 2 --out logs\hardware_integration\dht_serial.log
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
    ap.add_argument("--duration", type=float, default=30.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--send", default="",
                    help="Command to send (after --send-delay). Empty = capture only.")
    ap.add_argument("--send-delay", type=float, default=2.0,
                    help="Seconds to wait after opening port before sending --send.")
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
            print("PROBE_FAIL " + str(e))
            return 2

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1.0)
    except Exception as e:  # noqa
        print("OPEN_FAIL " + str(e))
        return 2

    time.sleep(0.2)
    out = open(args.out, "w", encoding="utf-8") if args.out else None

    if args.send:
        time.sleep(args.send_delay)
        ser.write((args.send + "\r\n").encode("utf-8"))
        sys.stdout.write("SENT: " + args.send + "\n")
        sys.stdout.flush()

    t0 = time.time()
    sys.stdout.write("CAPTURE_START duration=%.1f\n" % args.duration)
    sys.stdout.flush()
    try:
        while time.time() - t0 < args.duration:
            try:
                line = ser.readline()
            except Exception:  # noqa
                break
            if line:
                try:
                    s = line.decode("utf-8", "replace")
                except Exception:  # noqa
                    s = repr(line)
                sys.stdout.write(s)
                sys.stdout.flush()
                if out:
                    out.write(s)
                    out.flush()
    finally:
        ser.close()
        if out:
            out.close()
    sys.stdout.write("CAPTURE_END\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
