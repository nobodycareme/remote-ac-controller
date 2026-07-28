"""Simple atomic file storage for IR captures. No SQLite, no transactions."""
import hashlib, json, os, tempfile
from pathlib import Path

LEARNED_ROOT = Path("C:/example/remote-ac/Private/Firmware/IR/Learned")
DEFAULT_ROOT = Path("C:/example/remote-ac/Private/Firmware/IR/Learned")
CONFIG_PATH = Path(os.path.expanduser("~/.ir_simple_learner.json"))


def set_learned_root(path):
    """Update both LEARNED_ROOT and persist choice."""
    global LEARNED_ROOT
    LEARNED_ROOT = Path(path)
    LEARNED_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        CONFIG_PATH.write_text(json.dumps({"learned_root": str(LEARNED_ROOT)}), encoding="utf-8")
    except Exception:
        pass


def load_learned_root():
    """Load saved choice from config, fall back to default."""
    try:
        if CONFIG_PATH.exists():
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if cfg.get("learned_root"):
                p = Path(cfg["learned_root"])
                if p.exists() or p.parent.exists():
                    return p
    except Exception:
        pass
    return DEFAULT_ROOT


# Load saved root at import time (do NOT auto-create directory)
LEARNED_ROOT = load_learned_root()


def safe_filename(state_id: str) -> str:
    """Convert state ID to safe directory name."""
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in state_id)


def ensure_state_dir(state_id: str) -> Path:
    d = LEARNED_ROOT / safe_filename(state_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write data atomically: temp file, flush, fsync, verify, os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    tmp_path = Path(tmp)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        written = tmp_path.read_bytes()
        if len(written) != len(data):
            raise IOError(f"write length mismatch: {len(written)} vs {len(data)}")
        if hashlib.sha256(written).hexdigest() != hashlib.sha256(data).hexdigest():
            raise IOError("write sha256 mismatch")
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise


def atomic_write_json(path: Path, obj: dict) -> None:
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)
    atomic_write_bytes(path, text.encode("utf-8"))


def save_state(state_id: str, definition: dict) -> Path:
    d = ensure_state_dir(state_id)
    p = d / "state.json"
    atomic_write_json(p, definition)
    return p


def save_capture(state_id: str, capture_index: int, frame: bytes, meta: dict) -> Path:
    d = ensure_state_dir(state_id)
    cap_id = f"capture_{capture_index:03d}"
    bin_path = d / f"{cap_id}.bin"
    json_path = d / f"{cap_id}.json"
    atomic_write_bytes(bin_path, frame)
    sha = hashlib.sha256(frame).hexdigest()
    meta.update({"captureIndex": capture_index, "length": len(frame), "sha256": sha,
                 "source": "ZJ-IR-V2 external learn", "physicalValidation": False})
    atomic_write_json(json_path, meta)
    return bin_path


def save_comparison(state_id: str, frames: list, diff: dict) -> Path:
    d = ensure_state_dir(state_id)
    p = d / "comparison.json"
    atomic_write_json(p, diff)
    return p


def save_canonical(state_id: str, capture_index: int, frame: bytes) -> Path:
    d = ensure_state_dir(state_id)
    bin_path = d / "canonical.bin"
    json_path = d / "canonical.json"
    atomic_write_bytes(bin_path, frame)
    sha = hashlib.sha256(frame).hexdigest()
    import datetime
    atomic_write_json(json_path, {
        "sourceCapture": f"capture_{capture_index:03d}",
        "length": len(frame), "sha256": sha,
        "selectedAt": datetime.datetime.now().isoformat(),
        "physicalValidation": False,
    })
    return bin_path


def list_states() -> list:
    if not LEARNED_ROOT.exists():
        return []
    result = []
    for d in sorted(LEARNED_ROOT.iterdir()):
        if d.is_dir() and (d / "state.json").exists():
            result.append(d.name)
    return result


def load_state(state_id: str) -> dict:
    d = LEARNED_ROOT / safe_filename(state_id)
    p = d / "state.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_capture_frames(state_id: str) -> list:
    """Load all capture frames for a state."""
    d = LEARNED_ROOT / safe_filename(state_id)
    frames = []
    for i in range(1, 4):
        bp = d / f"capture_{i:03d}.bin"
        if bp.exists():
            frames.append(bp.read_bytes())
    return frames


def load_capture_meta(state_id: str, capture_index: int) -> dict:
    d = LEARNED_ROOT / safe_filename(state_id)
    p = d / f"capture_{capture_index:03d}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
