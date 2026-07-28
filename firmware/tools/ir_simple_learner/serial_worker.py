"""Serial worker thread for IR Simple Learner. One thread, one queue."""
import json, queue, threading, time
from typing import Callable, Optional

try:
    import serial
    import serial.tools.list_ports
    HAS_PYSERIAL = True
except ImportError:
    HAS_PYSERIAL = False


def find_ch9102():
    """Find all CH9102 devices (VID=0x1A86, PID=0x55D4)."""
    if not HAS_PYSERIAL:
        return []
    ports = []
    for p in serial.tools.list_ports.comports():
        if p.vid == 0x1A86 and p.pid == 0x55D4:
            ports.append({"device": p.device, "vid": f"0x{p.vid:04X}", "pid": f"0x{p.pid:04X}", "desc": p.description})
    return ports


def list_all_ports():
    """List all serial ports."""
    if not HAS_PYSERIAL:
        return []
    return [{"device": p.device, "desc": p.description or ""} for p in serial.tools.list_ports.comports()]


class SerialWorker:
    """Background thread for serial I/O. GUI reads events from a queue."""
    def __init__(self):
        self.queue = queue.Queue()
        self.ser: Optional[serial.Serial] = None
        self.running = False
        self.cancel_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self, port: str, baudrate: int = 115200):
        """Open serial and start reader thread."""
        if not HAS_PYSERIAL:
            self.queue.put({"type": "ERROR", "message": "pyserial not installed"})
            return
        try:
            # Windows only supports exclusive=True; ignore exclusive parameter
            self.ser = serial.Serial(port, baudrate, timeout=0.1, write_timeout=1.0)
        except Exception as e:
            # Friendly Chinese error
            msg = str(e)
            if "PermissionError" in msg or "拒绝访问" in msg:
                friendly = f"{port} 被其他程序占用。请关闭串口监视器、PlatformIO monitor或其他串口工具后重试。"
            elif "could not open" in msg:
                friendly = f"无法打开 {port}。检查设备连接或端口号。"
            else:
                friendly = msg
            self.queue.put({"type": "ERROR", "message": friendly})
            return
        self.running = True
        self.cancel_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop reader thread and close serial."""
        self.running = False
        self.cancel_event.set()
        if self.ser and self.ser.is_open:
            self._wake_read()
        if self.thread:
            self.thread.join(timeout=3.0)
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None

    def write_line(self, text: str):
        """Write a line to serial."""
        if self.ser and self.ser.is_open:
            self.ser.write((text + "\n").encode("utf-8"))
            self.ser.flush()

    def _wake_read(self):
        """Attempt to cancel blocking read."""
        if self.ser:
            try:
                self.ser.cancel_read()
            except Exception:
                pass

    def _run(self):
        """Background reader loop."""
        buf = ""
        while self.running:
            try:
                if self.ser and self.ser.is_open and self.ser.in_waiting > 0:
                    chunk = self.ser.read(self.ser.in_waiting).decode("utf-8", errors="replace")
                    buf += chunk
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if line.startswith("{"):
                            try:
                                evt = json.loads(line)
                                self.queue.put(evt)
                            except Exception:
                                self.queue.put({"type": "RAW", "text": line})
            except Exception:
                time.sleep(0.05)
            else:
                time.sleep(0.02)

    def is_alive(self) -> bool:
        return self.thread is not None and self.thread.is_alive()
