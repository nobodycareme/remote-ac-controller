#!/usr/bin/env python
"""CH9102 cross-check enumeration helper (read-only, never opens ports).

Called by tools/dev.ps1 (Resolve-Ch9102Port) as the pySerial verification
channel. Matches strictly by NUMERIC vid/pid (0x1A86 / 0x55D4) -- never by
friendly-name substring. Prints a single JSON object to stdout:

  {"available": bool, "ports": [{device, vid, pid, hwid, description,
                                 manufacturer, serial_number, location}]}

If pySerial is not importable in the project-controlled Python environment,
prints {"available": false, "ports": []} and exits 0 (caller falls back to
the PowerShell PnP/CIM channels). This script must never install packages.
"""
import json
import sys

TARGET_VID = 0x1A86
TARGET_PID = 0x55D4


def main() -> int:
    try:
        from serial.tools import list_ports
    except Exception:
        print(json.dumps({"available": False, "ports": []}))
        return 0

    ports = []
    try:
        for p in list_ports.comports():
            if p.vid == TARGET_VID and p.pid == TARGET_PID:
                ports.append({
                    "device": p.device,
                    "vid": p.vid,
                    "pid": p.pid,
                    "hwid": p.hwid,
                    "description": p.description,
                    "manufacturer": p.manufacturer,
                    "serial_number": p.serial_number,
                    "location": p.location,
                })
    except Exception:
        # Enumeration failure is NOT "device absent"; report channel unusable.
        print(json.dumps({"available": False, "ports": []}))
        return 0

    print(json.dumps({"available": True, "ports": ports}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
