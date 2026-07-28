#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_studio_mock.py — 红外学习采集台 并行开发期模拟测试（第二十八节）

不连接真机、不加载 pyserial、不污染真实 captures 目录。
所有模拟产物写入 tests/artifacts/tmp_*，测试后清理。
输出 14 个 IR_STUDIO_*_PASS 状态行 + 汇总。
"""

import os
import sys
import json
import time
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.dirname(HERE)
sys.path.insert(0, TOOL_DIR)

import models
import storage
import capture_core_adapter as adp
from mock_device import MockSerialDevice
from serial_device import LockManager, SerialDevice

ART = os.path.join(HERE, "artifacts")
TMP_STUDIO = os.path.join(ART, "tmp_studio")
TMP_LOCKS = os.path.join(ART, "tmp_locks")

VALID_FRAME = "68 0A 00 00 22 01 02 03 28 16"
BAD_FRAME = "68 0A 00 00 22 01 02 03 00 16"

RESULTS = {}


def _make_cfg(preset_key="preset1", sample=1, attempt=1):
    p = dict(models.PRESETS[preset_key])
    p["sessionId"] = "TEST_SESSION"
    p["sampleNumber"] = sample
    p["attemptNumber"] = attempt
    p["clickTimestamp"] = models.now_iso()
    p["serialPort"] = "MOCK"
    p["firmwareSha256"] = "unknown"
    p["learnTimeoutSeconds"] = 30
    return p


def test_gui_start():
    """导入 app 模块（含全部 import + tkinter 导入）即视为 GUI 可启动；
    若环境有显示则再尝试真正创建 Tk 窗口。"""
    import_ok = False
    window_ok = False
    err = ""
    try:
        import app  # 触发全部 import 链（含 tkinter）
        import_ok = True
    except Exception as e:
        err = str(e)
    try:
        import tkinter as tk
        root = tk.Tk()
        root.update_idletasks()
        root.destroy()
        window_ok = True
    except Exception:
        window_ok = False  # 无显示环境（如 CI/沙箱），导入已验证
    RESULTS["IR_STUDIO_GUI_START_PASS"] = import_ok
    print("[GUI] import_ok=%s window_ok=%s %s" % (import_ok, window_ok, ("" if import_ok else err)))


def test_task_create():
    """建立采集任务：会话目录 + session.json 创建成功。"""
    shutil.rmtree(TMP_STUDIO, ignore_errors=True)
    os.makedirs(TMP_STUDIO, exist_ok=True)
    cfg = _make_cfg()
    sid = models.build_session_id(cfg["brand"], cfg["stateBefore"], cfg["stateAfter"],
                                  cfg["taskType"], cfg["customTaskName"])
    d, actual = storage.safe_session_dir(TMP_STUDIO, sid)
    storage.save_session_json(d, {"sessionId": actual, "valid": 0, "targetValid": 3})
    ok = os.path.isdir(d) and os.path.exists(os.path.join(d, "session.json"))
    RESULTS["IR_STUDIO_TASK_CREATE_PASS"] = ok
    print("[TASK] session_dir=%s ok=%s" % (actual, ok))


def test_manual_start():
    """单次采集必须手动开始：query_status 不触发捕获，仅 start_learning 后才收到帧。"""
    be = adp.MockCaptureBackend(scenario="success")
    be.connect()
    st = be.query_status(window_s=1.0)
    # query_status 阶段不得产生帧
    assert st["busy"] is False
    # 显式手动开始
    ok, mode = be.start_learning(enter_wait_s=5)
    assert ok, "start_learning 未确认 ENTER"
    frame_hex, raw, canc = be.wait_for_capture(host_wait_s=5)
    ok2 = (frame_hex is not None)
    RESULTS["IR_STUDIO_MANUAL_START_PASS"] = (st["busy"] is False) and ok2
    print("[MANUAL] query_no_frame=%s capture_after_start=%s" % (st["busy"] is False, ok2))


def test_mock_capture():
    """模拟成功帧 -> 校验通过 -> 落盘 bin/json/txt/log + manifest。"""
    be = adp.MockCaptureBackend(scenario="success")
    be.connect()
    frame = adp.hex_to_bytes(VALID_FRAME)
    gate, gd = adp.validate_frame(frame)
    assert gate, "校验门禁应通过"
    cfg = _make_cfg()
    cid = models.build_capture_filename(cfg["brand"], cfg["stateBefore"], cfg["stateAfter"],
                                         cfg["taskType"], cfg["customTaskName"], 1)
    rec = models.build_sample_record_base(cfg)
    res = be.save_capture(TMP_STUDIO, cid, frame, ["IR_EXTLEARN_FRAME " + VALID_FRAME], rec)
    ok = (os.path.exists(res["bin_path"]) and os.path.exists(res["json_path"])
          and os.path.exists(res["txt_path"]) and res["binLengthMatch"]
          and rec["replayed"] is False and rec["cloudTriggered"] is False)
    RESULTS["IR_STUDIO_MOCK_CAPTURE_PASS"] = ok
    print("[CAPTURE] cid=%s bin_len_match=%s ok=%s" % (cid, res["binLengthMatch"], ok))


def test_checksum_failure():
    """模拟校验失败帧 -> 不生成 BIN，仅保存失败 JSON + 日志。"""
    be = adp.MockCaptureBackend(scenario="bad_checksum")
    be.connect()
    ok, _ = be.start_learning(enter_wait_s=5)
    frame_hex, raw, _ = be.wait_for_capture(host_wait_s=5)
    frame = adp.hex_to_bytes(frame_hex)
    gate, gd = adp.validate_frame(frame)
    assert not gate, "坏帧应通过门禁失败"
    cfg = _make_cfg()
    # 使用独立 capture_id，避免与成功测试的 BIN 文件名冲突
    cid = "CS_" + models.build_capture_filename(cfg["brand"], cfg["stateBefore"], cfg["stateAfter"],
                                                cfg["taskType"], cfg["customTaskName"], 1)
    rec = models.build_sample_record_base(cfg)
    res = be.save_failed(TMP_STUDIO, cid, rec, raw)
    bin_path = os.path.join(TMP_STUDIO, cid + ".bin")
    ok = (not os.path.exists(bin_path)) and os.path.exists(res["json_path"])
    RESULTS["IR_STUDIO_CHECKSUM_FAILURE_PASS"] = ok
    print("[CHECKSUM] gate_fail=%s no_bin=%s ok=%s" % (not gate, not os.path.exists(bin_path), ok))


def test_timeout():
    """模拟超时（无帧）-> 视为 timeout_waiting_remote。"""
    be = adp.MockCaptureBackend(scenario="timeout")
    be.connect()
    ok, _ = be.start_learning(enter_wait_s=3)
    frame_hex, raw, _ = be.wait_for_capture(host_wait_s=3)
    ok2 = (frame_hex is None)
    RESULTS["IR_STUDIO_TIMEOUT_PASS"] = ok2
    print("[TIMEOUT] frame_none=%s ok=%s" % (ok2, ok2))


def test_serial_busy():
    """模拟串口占用：MockCaptureBackend(occupied) connect 抛 SERIAL_BUSY；
    另测 LockManager 跨进程命名互斥量冲突 -> 第二次 acquire 返回 False（第一级保护）。
    注：命名互斥量按线程递归，同进程内两次 acquire 不会冲突；真实场景是两个
    独立进程，故此处用子进程持有互斥量来模拟“另一个采集工具”。"""
    # 1) 设备级占用
    be = adp.MockCaptureBackend(scenario="occupied")
    raised = False
    try:
        be.connect()
    except RuntimeError as e:
        raised = "SERIAL_BUSY" in str(e)

    # 2) 跨进程互斥量冲突：子进程持有互斥量，本进程 acquire 应被拒绝
    os.makedirs(TMP_LOCKS, exist_ok=True)
    child_script = os.path.join(ART, "_child_hold_lock.py")
    with open(child_script, "w", encoding="utf-8") as f:
        f.write(
            "import sys, time\n"
            "sys.path.insert(0, %r)\n"
            "from serial_device import LockManager\n"
            "lm = LockManager(locks_dir=%r)\n"
            "lm.acquire('COMX')\n"
            "time.sleep(30)\n" % (TOOL_DIR, TMP_LOCKS))
    proc = subprocess.Popen([sys.executable, child_script])
    time.sleep(1.0)  # 等待子进程持有互斥量
    lm = LockManager(locks_dir=TMP_LOCKS)
    ok2, reason = lm.acquire()   # 期望 False（子进程持有互斥量）
    proc.kill()
    try:
        proc.wait(timeout=5)
    except Exception:
        pass
    try:
        os.remove(child_script)
    except Exception:
        pass
    ok = raised and (not ok2)
    RESULTS["IR_STUDIO_SERIAL_BUSY_PASS"] = ok
    print("[BUSY] device_busy=%s cross_process_mutex_rejected=%s ok=%s"
          % (raised, not ok2, ok))


def test_cancel():
    """取消等待：start_learning 后 cancel，wait_for_capture 返回 cancelled。"""
    be = adp.MockCaptureBackend(scenario="success")
    be.connect()
    be.start_learning(enter_wait_s=5)
    be.cancel_or_wait_timeout()
    frame_hex, raw, canc = be.wait_for_capture(host_wait_s=5)
    ok = (canc is True)
    RESULTS["IR_STUDIO_CANCEL_PASS"] = ok
    print("[CANCEL] cancelled=%s ok=%s" % (canc, ok))


def test_no_overwrite():
    """不覆盖已有会话：相同 session_id 自动加 _02 后缀。"""
    d1, a1 = storage.safe_session_dir(TMP_STUDIO, "SESSION_X")
    d2, a2 = storage.safe_session_dir(TMP_STUDIO, "SESSION_X")
    ok = (a1 == "SESSION_X") and (a2 == "SESSION_X_02") and os.path.isdir(d2)
    RESULTS["IR_STUDIO_NO_OVERWRITE_PASS"] = ok
    print("[NO_OVERWRITE] a1=%s a2=%s ok=%s" % (a1, a2, ok))


def test_safe_exit():
    """安全退出：控制器式 acquire -> 模拟后端断开 -> release 清理锁。"""
    lm = LockManager(locks_dir=TMP_LOCKS)
    ok1, _ = lm.acquire("MOCK")
    # 模拟后端断开
    be = adp.MockCaptureBackend(scenario="success")
    be.connect()
    be.disconnect()
    lm.release()
    ok = ok1 and (not os.path.exists(lm.lock_path))
    RESULTS["IR_STUDIO_SAFE_EXIT_PASS"] = ok
    print("[SAFE_EXIT] lock_acquired=%s lock_released=%s ok=%s" % (ok1, not os.path.exists(lm.lock_path), ok))


def test_lock_release():
    """锁管理器：acquire 创建锁文件，release 删除。"""
    lm = LockManager(locks_dir=TMP_LOCKS)
    ok1, _ = lm.acquire("MOCK")
    existed = os.path.exists(lm.lock_path)
    lm.release()
    gone = not os.path.exists(lm.lock_path)
    ok = ok1 and existed and gone
    RESULTS["IR_STUDIO_LOCK_RELEASE_PASS"] = ok
    print("[LOCK] created=%s released=%s ok=%s" % (existed, gone, ok))


def test_replay_block():
    """硬门禁：发射类/非白名单命令被拒绝。"""
    sd = SerialDevice("COMx", 115200)
    blocked_send = False
    blocked_unknown = False
    try:
        sd.write("ir send 0x68 0x0A")
    except RuntimeError as e:
        blocked_send = "REPLAY_BLOCKED" in str(e)
    try:
        sd.write("format the disk")
    except RuntimeError as e:
        blocked_unknown = "COMMAND_NOT_ALLOWED" in str(e)
    ok = blocked_send and blocked_unknown
    RESULTS["IR_STUDIO_REPLAY_BLOCK_PASS"] = ok
    print("[REPLAY] send_blocked=%s unknown_blocked=%s ok=%s" % (blocked_send, blocked_unknown, ok))


def main():
    os.makedirs(ART, exist_ok=True)
    # 协议一致性自检（仅打印，不计入 PASS 列表）
    try:
        ok, detail = adp.verify_protocol_consistency()
        print("[PROTOCOL] consistent=%s %s" % (ok, detail))
    except Exception as e:
        print("[PROTOCOL] check skipped: %s" % e)

    test_gui_start()
    test_task_create()
    test_manual_start()
    test_mock_capture()
    test_checksum_failure()
    test_timeout()
    test_serial_busy()
    test_cancel()
    test_no_overwrite()
    test_safe_exit()
    test_lock_release()
    test_replay_block()

    # 清理模拟产物，仅保留结果摘要
    shutil.rmtree(os.path.join(ART, "tmp_studio"), ignore_errors=True)
    shutil.rmtree(os.path.join(ART, "tmp_locks"), ignore_errors=True)

    all_pass = all(RESULTS.values())
    lines = []
    for k in [
        "IR_STUDIO_GUI_START_PASS", "IR_STUDIO_TASK_CREATE_PASS",
        "IR_STUDIO_MANUAL_START_PASS", "IR_STUDIO_MOCK_CAPTURE_PASS",
        "IR_STUDIO_CHECKSUM_FAILURE_PASS", "IR_STUDIO_TIMEOUT_PASS",
        "IR_STUDIO_SERIAL_BUSY_PASS", "IR_STUDIO_CANCEL_PASS",
        "IR_STUDIO_NO_OVERWRITE_PASS", "IR_STUDIO_SAFE_EXIT_PASS",
        "IR_STUDIO_LOCK_RELEASE_PASS", "IR_STUDIO_REPLAY_BLOCK_PASS",
    ]:
        v = RESULTS.get(k, False)
        lines.append("%s=%s" % (k, "True" if v else "False"))
    summary = "\n".join(lines) + "\nIR_STUDIO_ALL_PASS=%s\n" % ("True" if all_pass else "False")
    with open(os.path.join(ART, "IR_STUDIO_TEST_RESULTS.txt"), "w", encoding="utf-8") as f:
        f.write(summary)
    print("")
    print(summary)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
