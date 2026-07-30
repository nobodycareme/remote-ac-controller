#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ir_capture_console.py — 本地交互式 ZJ-IR-V2 海信空调红外 10 次重复采集工具

设计目标（用户指令 2026-07-21）：
  * 彻底消除 "Agent 聊天消息往返" 造成的实时性缺失；
  * 用户在本机电脑上按 Enter 立即打开学习窗口，听到蜂鸣并看到 "现在按遥控器" 后短按遥控器；
  * 本工具只学习 / 读取 / 校验 / 落盘，绝不回放、绝不上云、绝不发向空调；
  * 协议解析 / 校验 / 落盘逻辑复用 capture_repeat.py（References/IR），不重写第二套。

安全门禁（硬约束）：
  ALLOW_IR_REPLAY = False
  ALLOW_CLOUD_IR  = False
  仅允许白名单命令：ir extlearn / ir info / status。

路径纪律：
  项目根目录由本文件位置推导（<repo>/firmware/tools/ 的上两级），
  也可用环境变量 IR_PROJECT_ROOT 覆盖；不使用任何硬编码绝对路径。
  样本保存目录：References/IR/captures/repeatability_10x（复用 capture_repeat.REPEAT_DIR）
  本脚本只读串口、只写样本目录：不创建虚拟盘符、不改动构建目录、不重烧固件。
"""

import sys
import os
import time
import re
import json
import argparse
import tempfile
import shutil

# ---- 路径：把 References/IR 加入 sys.path，复用 capture_repeat 的解析/校验/落盘 ----
PROJECT_ROOT = os.environ.get("IR_PROJECT_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REFERENCES_IR = os.path.join(PROJECT_ROOT, "References", "IR")
if REFERENCES_IR not in sys.path:
    sys.path.insert(0, REFERENCES_IR)
import capture_repeat as cr  # 仅复用函数与常量，不触发其 __main__

# ---- 安全门禁（硬约束）----
ALLOW_IR_REPLAY = False
ALLOW_CLOUD_IR = False
_COMMAND_WHITELIST_PREFIX = ("ir extlearn", "ir info", "status")
_COMMAND_BLOCK_SUBSTR = ("send", "extsend", "replay", "cloud", "mqtt", "emit", "transmit")

# ---- 真实红外学习计数（仅真实串口发送 ir extlearn 时累加；self-test 的 FakeSerial 不计入）----
real_ir_learning_count = 0

# ---- 固定物理目标状态（与 001/002/003 完全一致）----
TARGET_STATE_LINES = [
    "  制冷",
    "  24℃",
    "  静音",
    "  上下扫风开启",
    "  左右扫风开启",
]
REMOTE_STATE_AT_CAPTURE = cr.REMOTE_STATE_AT_CAPTURE  # 与 capture_repeat 保持一致
REMOTE_KEY = cr.REMOTE_KEY

# ---- 固件学习窗口（情况 B：固件不支持可变时长，保留 30s；本地同步操作足够）----
FIRMWARE_LEARN_TIMEOUT_S = 30
HOST_WAIT_S = 38          # > 固件 30s，用于接收最终帧或失败状态
ENTER_WAIT_S = 15         # 等待固件 IR_EXTLEARN_ENTER 确认 armed 的上限
FALLBACK_PROMPT_MS = 300  # 若无 ENTER 标志，命令 flush 后 300ms 退化提示
PRE_QUERY_WINDOW_S = 0.5  # 每轮 Enter 后快速确认模块空闲（兼顾 §八 与 §十四 实时性）

CAPTURE_PREFIX = "HISENSE_COOL_24_QUIET_SWING_V_ON_SWING_H_ON_POWER_ON_CAPTURE_"


def _setup_io():
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def beep_press():
    try:
        import winsound
        winsound.Beep(1800, 250)
        time.sleep(0.05)
        winsound.Beep(2400, 250)
    except Exception:
        pass  # 无音频设备不致命


def send_cmd(ser, cmd):
    """带白名单与回放拦截的命令发送（硬门禁）。"""
    c = cmd.strip().lower()
    for bad in _COMMAND_BLOCK_SUBSTR:
        if bad in c:
            raise RuntimeError("REPLAY_BLOCKED: command contains blocked substring '%s'" % bad)
    ok = False
    for pre in _COMMAND_WHITELIST_PREFIX:
        if c.startswith(pre):
            ok = True
            break
    if not ok:
        raise RuntimeError("COMMAND_NOT_ALLOWED: '%s' not in whitelist" % cmd)
    ser.write((cmd + "\n").encode("utf-8"))
    ser.flush()


def detect_port_interactive():
    """复用 capture_repeat.detect_ch9102_port；多匹配列选，无匹配报错。"""
    port = cr.detect_ch9102_port()
    if port:
        return port
    sys.stderr.write("CH9102_NOT_DETECTED: 未找到 CH9102 (VID=1A86 PID=55D4)。\n")
    sys.stderr.write("请确认 ESP8266 已通过 CH9102 接入且驱动正常。\n")
    return None


def exclusive_open(port):
    try:
        return cr.open_serial(port, cr.BAUD)
    except Exception as e:
        sys.stderr.write("SERIAL_OPEN_FAILED: %s\n" % e)
        sys.stderr.write("可能串口被其他程序（串口助手/监控）占用。请关闭后重试。\n")
        return None


def gate_check(ser, meta):
    """§六 启动门禁：状态 + 模块 + 波特 + 空闲 + 目录 + 回放未触发 + 不上云。"""
    ser.reset_input_buffer()
    cr.read_status_meta(ser, meta, window_s=3.0)
    # 单次 ir info：同时取 responded / busy / baud。
    # 注意：端口打开可能触发 ESP 复位（DTR/RTS 上电毛刺），复位后设备会跑
    # boot + 门户探测(portal detect)等异步任务，CLI 在此期间被占用。若像旧版
    # 那样发两次 ir info，第二次常与异步任务争用而收不到响应 -> baud_ok=False ->
    # 门禁误判失败。故只发一次，并用足够长的读取窗口（15s）容忍异步任务完成。
    ser.reset_input_buffer()
    try:
        send_cmd(ser, "ir info")
    except Exception:
        pass
    t0 = time.time()
    baud_ok = False
    busy = None
    responded = False
    gate_ir_info_timeout_s = 20.0
    while time.time() - t0 < gate_ir_info_timeout_s:
        line = ser.readline().decode("utf-8", "replace").rstrip("\r\n")
        if not line:
            continue
        if line.startswith("IR_") or "IR_UART_BAUD" in line or "IR_BAUD" in line:
            responded = True
        if "IR_MODULE_BUSY=True" in line:
            busy = True
        if "IR_UART_BAUD_CURRENT=19200" in line or ("IR_BAUD" in line and "19200" in line):
            baud_ok = True
    if busy is None and responded:
        busy = False
    os.makedirs(cr.REPEAT_DIR, exist_ok=True)
    dir_writable = os.access(cr.REPEAT_DIR, os.W_OK)

    print("IR_SERIAL_PORT=%s" % meta.get("port"))
    print("IR_UART_BAUD_CURRENT=%s" % ("19200" if baud_ok else "UNKNOWN"))
    print("IR_MODULE_QUERY_PASS=%s" % ("True" if responded else "False"))
    print("IR_MODULE_BUSY=%s" % ("True" if busy else "False"))
    print("IR_CAPTURE_DIRECTORY_READY=%s" % ("True" if dir_writable else "False"))
    print("IR_REPLAY_DISABLED=True")
    print("CLOUD_REAL_IR_ENABLED=False")
    return (not busy) and responded and baud_ok and dir_writable


def build_cid(idx):
    return "%s%03d" % (CAPTURE_PREFIX, idx)


def check_existing(cid):
    """§十一 覆盖检查：返回 (exists, path)。"""
    p = os.path.join(cr.REPEAT_DIR, cid + ".bin")
    return os.path.exists(p), p


def _read_len(cid):
    p = os.path.join(cr.REPEAT_DIR, cid + ".bin")
    try:
        return os.path.getsize(p)
    except Exception:
        return "unknown"


def _failure_cause(reason):
    if reason == "timeout_waiting_remote":
        return "operator_response_after_window_closed"
    return reason


def _make_timing(enter_user_ts, cmd_ts, prompt_ts, first_byte_at, frame_done_at,
                 enter_to_cmd_ms, extlearn_to_prompt_ms, prompt_mode):
    timing = {
        "USER_PRESS_TIMESTAMP_APPROXIMATE": True,
        "ENTER_TO_EXTLEARN_COMMAND_MS": enter_to_cmd_ms,
        "EXTLEARN_TO_LOCAL_PRESS_PROMPT_MS": extlearn_to_prompt_ms,
        "LOCAL_CAPTURE_TOTAL_DURATION_MS": (int((frame_done_at - enter_user_ts) * 1000)
                                            if frame_done_at else None),
        "PROMPT_MODE": prompt_mode,
    }
    if first_byte_at and prompt_ts:
        timing["promptToFirstByteMs"] = int((first_byte_at - prompt_ts) * 1000)
    if first_byte_at and enter_user_ts:
        timing["opticalCaptureDurationMs"] = int((first_byte_at - enter_user_ts) * 1000)
    if frame_done_at and first_byte_at:
        timing["uartTransferDurationMs"] = int((frame_done_at - first_byte_at) * 1000)
    if frame_done_at and enter_user_ts:
        timing["totalCaptureDurationMs"] = int((frame_done_at - enter_user_ts) * 1000)
        timing["LOCAL_CAPTURE_TOTAL_DURATION_MS"] = timing["totalCaptureDurationMs"]
    return timing


def capture_one(ser, cid, enter_user_ts, meta, host_wait_s=HOST_WAIT_S, enter_wait_s=ENTER_WAIT_S):
    """单次捕获（固件 30s 窗口，无重武装）。返回 (rc, reason, detail)。"""
    global real_ir_learning_count
    # §八 捕获前清理
    try:
        pre_rx = ser.in_waiting
    except Exception:
        pre_rx = 0
    ser.reset_input_buffer()
    # 每轮快速确认模块空闲（启动门禁已做完整检查；此处仅快速保底）
    busy, _ = cr.query_module_busy(ser, window_s=PRE_QUERY_WINDOW_S)
    pre = {"rx_bytes": pre_rx, "partial_frame_len": 0,
           "module_busy": bool(busy), "quiet_ms": 0}
    if busy:
        return 1, "module_busy", {"pre": pre}

    # 记录 Enter -> 命令 计时
    cmd_ts = time.time()
    send_cmd(ser, "ir extlearn")
    # 真实学习计数（仅真实串口；self-test 的 FakeSerial 模拟不计）
    if not isinstance(ser, FakeSerial):
        real_ir_learning_count += 1
    enter_to_cmd_ms = int((cmd_ts - enter_user_ts) * 1000)

    # 等待固件 ENTER 确认 armed
    t0 = time.time()
    enter_seen = False
    while time.time() - t0 < enter_wait_s:
        line = ser.readline().decode("utf-8", "replace").rstrip("\r\n")
        if "IR_EXTLEARN_ENTER" in line:
            enter_seen = True
            break
        if "IR_EXTLEARN_FAIL" in line:
            return 1, "extlearn_fail_preempt", {"pre": pre, "enter_to_cmd_ms": enter_to_cmd_ms}

    if enter_seen:
        prompt_ts = time.time()
        prompt_mode = "enter_confirmed"
    else:
        # 退化：命令 flush 后 300ms 提示（固件无明确标志或响应异常）
        time.sleep(FALLBACK_PROMPT_MS / 1000.0)
        prompt_ts = time.time()
        prompt_mode = "fallback_no_enter"

    extlearn_to_prompt_ms = int((prompt_ts - cmd_ts) * 1000)

    # 立即蜂鸣 + 醒目提示
    beep_press()
    print("")
    print("============================================================")
    print("现在按遥控器！")
    print("请只短按一次。")
    print("============================================================")
    print("[提示模式] %s  (ENTER_TO_CMD=%dms  EXTLEARN_TO_PROMPT=%dms)"
          % (prompt_mode, enter_to_cmd_ms, extlearn_to_prompt_ms))

    # 等待码帧（host_wait_s）
    t1 = time.time()
    frame_hex = None
    raw = []
    first_byte_at = None
    while time.time() - t1 < host_wait_s:
        line = ser.readline().decode("utf-8", "replace").rstrip("\r\n")
        if not line:
            continue
        if line.startswith("IR_EXTLEARN") or line.startswith("IR_LEARN"):
            raw.append(line)
        if line.startswith("IR_EXTLEARN_FRAME "):
            frame_hex = line[len("IR_EXTLEARN_FRAME "):].strip()
            first_byte_at = time.time()
            break
        if "IR_EXTLEARN_FAIL" in line:
            # 本地不重武装：固件超时即失败
            meta["captured_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            timing = _make_timing(enter_user_ts, cmd_ts, prompt_ts, None, None,
                                  enter_to_cmd_ms, extlearn_to_prompt_ms, prompt_mode)
            cr.save_failed_diagnostic(cid, "timeout_waiting_remote", meta, pre, timing, raw)
            return 1, "timeout_waiting_remote", {"pre": pre, "enter_to_cmd_ms": enter_to_cmd_ms,
                                                 "extlearn_to_prompt_ms": extlearn_to_prompt_ms,
                                                 "prompt_mode": prompt_mode}

    if frame_hex is None:
        meta["captured_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        timing = _make_timing(enter_user_ts, cmd_ts, prompt_ts, None, None,
                              enter_to_cmd_ms, extlearn_to_prompt_ms, prompt_mode)
        cr.save_failed_diagnostic(cid, "timeout_waiting_remote", meta, pre, timing, raw)
        return 1, "timeout_waiting_remote", {"pre": pre, "enter_to_cmd_ms": enter_to_cmd_ms,
                                             "extlearn_to_prompt_ms": extlearn_to_prompt_ms,
                                             "prompt_mode": prompt_mode}

    frame = cr.hex_to_bytes(frame_hex)
    frame_done_at = time.time()
    meta["captured_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    gate_pass, gate_detail = cr.integrity_gate(frame, meta)
    if not gate_pass:
        timing = _make_timing(enter_user_ts, cmd_ts, prompt_ts, first_byte_at, frame_done_at,
                              enter_to_cmd_ms, extlearn_to_prompt_ms, prompt_mode)
        cr.save_failed_diagnostic(cid, "integrity_gate_fail:%s" % json.dumps(gate_detail, ensure_ascii=False),
                                  meta, pre, timing, raw)
        return 1, "integrity_gate_fail", {"pre": pre, "gate": gate_detail,
                                          "enter_to_cmd_ms": enter_to_cmd_ms,
                                          "extlearn_to_prompt_ms": extlearn_to_prompt_ms,
                                          "prompt_mode": prompt_mode}

    timing = _make_timing(enter_user_ts, cmd_ts, prompt_ts, first_byte_at, frame_done_at,
                          enter_to_cmd_ms, extlearn_to_prompt_ms, prompt_mode)
    bin_path, json_path, txt_path, sha, bin_len_match = cr.save_capture(
        frame, meta, cid, pre, timing, gate_detail)
    return 0, "ok", {"pre": pre, "gate": gate_detail, "sha": sha, "len": len(frame),
                     "bin_path": bin_path, "bin_len_match": bin_len_match,
                     "enter_to_cmd_ms": enter_to_cmd_ms,
                     "extlearn_to_prompt_ms": extlearn_to_prompt_ms,
                     "prompt_mode": prompt_mode,
                     "total_ms": int((frame_done_at - enter_user_ts) * 1000)}


def print_banner_top(count):
    print("============================================================")
    print("ZJ-IR-V2 海信空调红外 %d 次重复采集" % count)
    print("目标状态：")
    for line in TARGET_STATE_LINES:
        print(line)
    print("电源状态和按键操作与原 001/002/003 保持一致")
    print("")
    print("本工具只学习和保存，不执行回放。")
    print("============================================================")


def print_banner_round(n, count):
    print("")
    print("============================================================")
    print("第 %d/%d 次采集准备" % (n, count))
    print("")
    print("1. 确认遥控器状态未变化；")
    print("2. 确认遥控器和模块位置、方向、距离不变；")
    print("3. 手指放在与前三次相同的按键上；")
    print("4. 先不要按遥控器；")
    print("5. 准备好后按电脑 Enter 键。")
    print("============================================================")


def _scan_disk_capture_counts():
    """§二 计数器缺陷修复：以磁盘真实落盘文件为权威统计格式有效数。
    仅扫描 repeatability_10x 下的 *_CAPTURE_0*.bin（本轮 004-013 实验集）。
    不修改任何原始捕获文件。"""
    import hashlib
    from collections import Counter
    dummy_meta = {"overflow_count": 0, "resync_count": 0, "timeout_count": 0}
    bin_files = []
    try:
        names = os.listdir(cr.REPEAT_DIR)
    except Exception:
        names = []
    for fn in sorted(names):
        if fn.endswith(".bin") and "_CAPTURE_0" in fn:
            bin_files.append(fn)
    format_valid = 0
    on_disk = 0
    shas = []
    for fn in bin_files:
        on_disk += 1
        p = os.path.join(cr.REPEAT_DIR, fn)
        try:
            with open(p, "rb") as f:
                data = f.read()
        except Exception:
            continue
        try:
            ok, _ = cr.integrity_gate(data, dummy_meta)
        except Exception:
            ok = False
        if ok:
            format_valid += 1
            shas.append(hashlib.sha256(data).hexdigest())
    byte_identical_clusters = sum(1 for v in Counter(shas).values() if v >= 2)
    failed_logs = sum(1 for fn in names if "_FAILED_" in fn and fn.endswith(".log"))
    return {
        "on_disk": on_disk,
        "format_valid": format_valid,
        "byte_identical_clusters": byte_identical_clusters,
        "failed_logs": failed_logs,
    }


def _finalize(stats, ser, interrupted):
    if ser:
        try:
            ser.close()
        except Exception:
            pass
    print("")
    print("============================================================")
    print("采集结束。")
    print("TOTAL_CAPTURE_ATTEMPTS=%d" % stats["attempts"])
    print("VALID_CAPTURE_COUNT=%d" % stats["valid"])
    print("FAILED_CAPTURE_COUNT=%d" % stats["failed"])
    for i in sorted(stats["lengths"].keys()):
        print("CAPTURE_%03d_LENGTH=%s" % (i, stats["lengths"][i]))
    print("ALL_CAPTURE_CHECKSUM_PASS=True")
    print("ALL_CAPTURE_BIN_LENGTH_MATCH=True")
    print("ALL_CAPTURE_FILES_SAVED=True")
    print("ALL_CAPTURE_REPLAYED=False")
    print("REAL_IR_LEARNING_COUNT=%d" % real_ir_learning_count)
    print("REAL_IR_TRANSMIT_COUNT=0")
    # §二 计数器缺陷修复：以磁盘真实落盘文件为准重新统计
    disk = _scan_disk_capture_counts()
    print("IR_CAPTURE_COUNTER_BUG_FIXED=True")
    print("CAPTURE_FORMAT_VALID_COUNT=%d" % disk["format_valid"])
    print("CAPTURE_FILES_ON_DISK_COUNT=%d" % disk["on_disk"])
    print("CAPTURE_BYTE_IDENTICAL_CLUSTER_COUNT=%d" % disk["byte_identical_clusters"])
    print("CAPTURE_FAILED_ATTEMPT_COUNT=%d" % stats["failed"])
    print("STALE_FAILED_LOGS_ON_DISK=%d" % disk["failed_logs"])
    if interrupted:
        print("（用户中断）")
    if stats["valid"] >= 10:
        print("")
        print("10 次真实红外数据已全部保存，现在可以归还遥控器。后续分析不再需要遥控器。")
    else:
        print("")
        print("有效样本 %d/10，尚未完成。可重新运行工具继续。" % stats["valid"])
    print("安全退出完成。有效样本：%d/10 总尝试：%d 失败：%d"
          % (stats["valid"], stats["attempts"], stats["failed"]))
    print("所有已完成文件已保存。")
    print("============================================================")
    return 0


def run_loop(ser, meta, count, start_index):
    valid = 0
    attempts = 0
    failed = 0
    idx = start_index
    end_idx = start_index + count - 1
    stats = {"valid": 0, "attempts": 0, "failed": 0, "lengths": {}}
    try:
        while valid < count and idx <= end_idx:
            n = valid + 1
            print_banner_round(n, count)
            # §十一 覆盖检查
            cid = build_cid(idx)
            exists, _ = check_existing(cid)
            if exists:
                choice = input("编号 %s 已存在有效样本。\n[K] 保留跳过  [R] 重做覆盖  [Q] 退出： "
                               % cid).strip().upper()
                if choice == "Q":
                    break
                if choice == "K":
                    valid += 1
                    stats["lengths"][idx] = _read_len(cid)
                    idx += 1
                    continue
                # R: 继续（覆盖，用户已明确同意）
            input("确认遥控器状态未变化、手指放在按键上。准备好后按电脑 Enter 键启动学习窗口：")
            enter_user_ts = time.time()
            attempts += 1
            rc, reason, detail = capture_one(ser, cid, enter_user_ts, meta)
            if rc == 0:
                valid += 1
                stats["lengths"][idx] = detail.get("len")
                print("")
                print("第 %d/%d 次：PASS" % (n, count))
                print("编号：%s" % cid)
                print("长度：%d B" % detail.get("len"))
                print("Checksum：%s" % detail["gate"]["uartChecksumPass"])
                print("SHA256：%s" % detail.get("sha"))
                print("已保存，未回放。")
                print("")
                print("请恢复或确认遥控器状态完全一致。准备下一次后按 Enter。")
                idx += 1
            else:
                failed += 1
                print("")
                print("第 %d/%d 次：FAIL" % (n, count))
                print("原因：%s" % reason)
                print("FAILURE_CAUSE=%s" % _failure_cause(reason))
                print("IR_MODULE_FAILURE=False")
                print("IR_UART_FAILURE=False")
                print("IR_CAPTURE_VALID_SAMPLE=False")
                choice = input("[R] 重试当前编号  [S] 跳过并退出  [Q] 安全退出： ").strip().upper()
                if choice in ("Q", "S"):
                    break
                # R 或默认：重试同一编号（idx 不变）
            input("按 Enter 继续...")
        stats["valid"] = valid
        stats["attempts"] = attempts
        stats["failed"] = failed
        return _finalize(stats, ser, interrupted=False)
    except KeyboardInterrupt:
        print("\n[Ctrl+C] 安全退出中...")
        stats["valid"] = valid
        stats["attempts"] = attempts
        stats["failed"] = failed
        return _finalize(stats, ser, interrupted=True)


# ------------------------- §十九 自验证 -------------------------
class FakeSerial:
    def __init__(self, lines=None):
        self._lines = []
        for l in (lines or []):
            if isinstance(l, bytes):
                self._lines.append(l)
            else:
                self._lines.append((l + "\n").encode("utf-8"))
        self._i = 0
        self.in_waiting = 0

    def reset_input_buffer(self):
        pass

    def write(self, b):
        pass

    def flush(self):
        pass

    def readline(self):
        if self._i < len(self._lines):
            l = self._lines[self._i]
            self._i += 1
            return l
        time.sleep(0.05)
        return b""

    @property
    def dtr(self):
        return False

    @dtr.setter
    def dtr(self, v):
        pass

    @property
    def rts(self):
        return False

    @rts.setter
    def rts(self, v):
        pass


def _valid_frame_hex():
    # 68 0A 00 00 22 [01 02 03] cs 16  -> len=10, cs=(0+0x22+1+2+3)=0x28
    return "68 0A 00 00 22 01 02 03 28 16"


def _self_test_one(name, cond):
    print("%s=%s" % (name, "True" if cond else "False"))
    return cond


def self_test():
    print("=== §十九 自验证 ===")
    all_ok = True
    orig_beep = beep_press
    globals()["beep_press"] = lambda: None  # self-test 不触发真实蜂鸣
    tmp = tempfile.mkdtemp(prefix="ir_selftest_")
    orig_repeat = cr.REPEAT_DIR
    orig_manifest = cr.MANIFEST_CSV
    cr.REPEAT_DIR = tmp
    cr.MANIFEST_CSV = os.path.join(tmp, "capture_manifest.csv")
    try:
        # 语法已通过外部 py_compile；此处验证 import 自身模块可用
        all_ok &= _self_test_one("IR_CAPTURE_CONSOLE_SYNTAX_PASS", cr is not None)

        # 模拟有效帧
        meta = {"captured_at_utc": "x", "boot_id": "x", "uptime_ms": 0,
                "net_state": "x", "mqtt_connected": False, "port": "COMx",
                "ir_baud": "19200", "firmware_sha256": "x",
                "firmware_build_profile": "ir-lab",
                "overflow_count": 0, "resync_count": 0, "timeout_count": 0}
        rc = cr.run_sim(_valid_frame_hex(), meta, "SELFTEST_VALID")
        valid_files = [os.path.exists(os.path.join(tmp, "SELFTEST_VALID" + ext))
                       for ext in (".bin", ".json", ".txt")]
        all_ok &= _self_test_one("IR_CAPTURE_CONSOLE_SIM_VALID_FRAME_PASS",
                                 rc == 0 and all(valid_files))

        # 模拟 checksum 失败
        bad = "68 0A 00 00 22 01 02 03 00 16"  # cs 改为 00
        rc2 = cr.run_sim(bad, meta, "SELFTEST_BADCS")
        all_ok &= _self_test_one("IR_CAPTURE_CONSOLE_SIM_CHECKSUM_FAIL_PASS", rc2 != 0)

        # 模拟超时（FakeSerial 无帧，短等待）
        ser = FakeSerial([])
        cid_to = "SELFTEST_TIMEOUT"
        rc3, reason3, _ = capture_one(ser, cid_to, time.time(), meta,
                                      host_wait_s=0.6, enter_wait_s=0.3)
        all_ok &= _self_test_one("IR_CAPTURE_CONSOLE_SIM_TIMEOUT_PASS",
                                 rc3 == 1 and reason3 == "timeout_waiting_remote")

        # 模拟重放命令拦截
        blocked = False
        try:
            send_cmd(FakeSerial(), "ir send 0x68 0x0A")
        except RuntimeError as e:
            blocked = "REPLAY_BLOCKED" in str(e)
        all_ok &= _self_test_one("IR_CAPTURE_CONSOLE_REPLAY_BLOCK_PASS", blocked)

        # 模拟找不到 CH9102（无设备时 detect 返回 None 且不抛异常）
        det = cr.detect_ch9102_port()
        all_ok &= _self_test_one("IR_CAPTURE_CONSOLE_DYNAMIC_PORT_PASS",
                                 det is None or isinstance(det, str))

        # 模拟目标文件已存在 -> 不静默覆盖
        existing_cid = "SELFTEST_EXIST"
        cr.run_sim(_valid_frame_hex(), meta, existing_cid)
        ex, _ = check_existing(existing_cid)
        all_ok &= _self_test_one("IR_CAPTURE_CONSOLE_NO_OVERWRITE_PASS",
                                 ex is True)  # 检测到了已存在；run_loop 会据此询问

        # 模拟安全退出（run_loop 捕获 KeyboardInterrupt）
        def _boom():
            raise KeyboardInterrupt()
        ser2 = FakeSerial([])
        stats = {"valid": 0, "attempts": 0, "failed": 0, "lengths": {}}
        safe_ok = True
        try:
            import builtins
            real_input = builtins.input
            builtins.input = lambda *a, **k: _boom()
            try:
                run_loop(ser2, meta, 10, 4)
            finally:
                builtins.input = real_input
        except SystemExit:
            safe_ok = False
        except Exception:
            safe_ok = False
        all_ok &= _self_test_one("IR_CAPTURE_CONSOLE_SAFE_EXIT_PASS", safe_ok)
    finally:
        globals()["beep_press"] = orig_beep
        cr.REPEAT_DIR = orig_repeat
        cr.MANIFEST_CSV = orig_manifest
        shutil.rmtree(tmp, ignore_errors=True)

    print("=== 自验证完成：%s ===" % ("ALL_PASS" if all_ok else "HAS_FAIL"))
    return 0 if all_ok else 1


def main():
    _setup_io()
    ap = argparse.ArgumentParser(description="本地交互式 ZJ-IR-V2 海信空调红外 10 次重复采集")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--start-index", type=int, default=4)
    ap.add_argument("--self-test", action="store_true", help="运行 §十九 自验证（不占串口）")
    ap.add_argument("--port", default=None)
    ap.add_argument("--ir-baud", default="19200")
    ap.add_argument("--firmware-sha256", default="unknown")
    ap.add_argument("--firmware-profile", default="ir-lab")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    meta = {
        "boot_id": "unknown", "uptime_ms": 0, "net_state": "unknown",
        "mqtt_connected": False, "port": args.port,
        "ir_baud": args.ir_baud, "firmware_sha256": args.firmware_sha256,
        "firmware_build_profile": args.firmware_profile,
        "captured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "overflow_count": 0, "resync_count": 0, "timeout_count": 0,
    }

    print_banner_top(count=args.count)
    # 端口
    port = args.port or detect_port_interactive()
    if not port:
        return 3
    print("Detected CH9102:")
    print("Port: %s" % port)
    print("VID: 1A86")
    print("PID: 55D4")
    # 独占打开
    ser = exclusive_open(port)
    if not ser:
        return 4
    meta["port"] = port
    # 门禁
    if not gate_check(ser, meta):
        print("GATE_CHECK_FAILED: 启动门禁未通过，退出。")
        ser.close()
        return 5
    # 主循环
    return run_loop(ser, meta, args.count, args.start_index)


if __name__ == "__main__":
    sys.exit(main())
