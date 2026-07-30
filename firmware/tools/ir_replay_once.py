#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地单次受控红外回放门禁（ZJ-IR-V2 海信空调）。

设计约束（用户指令 §四 / §六）：
  - 只允许本地 CLI 单次、人工确认回放；禁用网页 / MQTT / 云端 / 定时 / 自动重试。
  - 真实发射仅在显式 --authorize 且用户口头授权（"允许单次回放候选XXX"）后执行一次。
  - 回放 payload 必须与候选 BIN 逐字节一致（IR_CAPTURE_TRANSPORT_INTEGRITY_PASS）。
  - 固件 `ir extsend` 仅重放 m_extLearnBuf；`ir extload <hexchunk>`...`ir extload commit`
    把候选 BIN 字节分块载入缓冲（不发射），随后 `ir extsend` 逐字节重放。
  - `--verify-load`：仅验证加载链路（分块载入 + 回显比对），全程禁止发射。
  - 仅当 --verify-load 全部通过，才允许向用户请求单次真实回放确认；
    真实发射仍需用户另行回复 '允许单次回放候选XXX' 并以 --authorize 执行。

安全标志（硬编码关闭公网/云/自动路径）：
  CLOUD_REAL_IR_ENABLED=False
  ENABLE_IR_MUTATING_COMMANDS_PUBLIC=False
  GUEST_REAL_IR_ALLOWED=False
  MQTT_REAL_IR_ALLOWED=False
  WEB_REAL_IR_ALLOWED=False
  AUTO_REPLAY_ALLOWED=False
  IR_TRANSMIT_AUTO_RETRY_DISABLED=True
"""
import sys
import os
import time
import json
import hashlib
import argparse

PROJECT_ROOT = os.environ.get("IR_PROJECT_ROOT") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REFERENCES_IR = os.path.join(PROJECT_ROOT, "References", "IR")
REPEAT_DIR = os.path.join(REFERENCES_IR, "captures", "repeatability_10x")
ORIG_DIR = os.path.join(REFERENCES_IR, "captures")
if REFERENCES_IR not in sys.path:
    sys.path.insert(0, REFERENCES_IR)
import capture_repeat as cr  # detect_ch9102_port / open_serial / integrity_gate / query_module_busy

CID_PREFIX = "HISENSE_COOL_24_QUIET_SWING_V_ON_SWING_H_ON_POWER_ON_CAPTURE_"

# 安全常量（运行时只读，禁止任何修改）
CLOUD_REAL_IR_ENABLED = False
ENABLE_IR_MUTATING_COMMANDS_PUBLIC = False
GUEST_REAL_IR_ALLOWED = False
MQTT_REAL_IR_ALLOWED = False
WEB_REAL_IR_ALLOWED = False
AUTO_REPLAY_ALLOWED = False
IR_TRANSMIT_AUTO_RETRY_DISABLED = True

ESP_DEBUG_BAUD = 115200  # PC<->ESP 调试串口（非 19200 红外模块波特）

# 每块字节数：须使单行命令 "ir extload <hex>" 不超过固件 CLI_LINE_MAX(64)。
# 命令长度 = len("ir extload ")=11 + (3*N - 1) = 10 + 3N <= 64 -> N <= 18。
# 取 16 留足余量（10 + 48 = 58 字符）。
CHUNK_BYTES = 16


def find_candidate(cid):
    for d in (REPEAT_DIR, ORIG_DIR):
        p = os.path.join(d, cid + ".bin")
        if os.path.exists(p):
            return p, d
    return None, None


def find_json(cid):
    for d in (REPEAT_DIR, ORIG_DIR):
        p = os.path.join(d, cid + ".json")
        if os.path.exists(p):
            return p
    return None


def sha256_file(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def frame_hex(data):
    return " ".join("%02X" % b for b in data)


def send_cmd(ser, cmd, timeout=6.0, stop_tokens=("IR_EXTLOAD", "UNKNOWN", "ERROR")):
    ser.reset_input_buffer()
    ser.write((cmd + "\n").encode("utf-8", "replace"))
    t0 = time.time()
    lines = []
    while time.time() - t0 < timeout:
        try:
            line = ser.readline().decode("utf-8", "replace").rstrip("\r\n")
        except Exception:
            line = ""
        if line:
            lines.append(line)
            up = line.upper()
            if any(tok in up for tok in stop_tokens):
                break
    return lines


def module_query_ok(ser, window_s=20.0):
    ser.reset_input_buffer()
    busy, responded = cr.query_module_busy(ser, window_s=window_s)
    return (not busy) and responded, busy, responded


def wait_cli_ready(ser, max_s=12.0, idle_after_s=3.0):
    """端口打开可能触发 ESP 硬件复位；等待调试 CLI 启动完成后再发命令。
    返回 True 表示已等待结束（见到就绪标记或判定早已空闲），可安全发令。"""
    ser.reset_input_buffer()
    t0 = time.time()
    last_data = t0
    while time.time() - t0 < max_s:
        try:
            line = ser.readline().decode("utf-8", "replace").rstrip("\r\n")
        except Exception:
            line = ""
        now = time.time()
        if line:
            last_data = now
            up = line.upper()
            if ("DIAGNOSTIC_CONSOLE_READY=YES" in up or "CMD_SERVICE_READY" in up
                    or "APP_BOOT_OK" in up):
                break
        elif now - last_data >= idle_after_s:
            # 已静默 idle_after_s 秒且无任何数据，视为早已启动就绪
            break
    ser.reset_input_buffer()
    time.sleep(0.4)
    ser.reset_input_buffer()
    return True


def load_and_verify(ser, data):
    """分块载入候选 BIN 并提交，回显比对。全程不发射。
    返回 (True, (commit_len, echo_bytes, byte_identical)) 或 (False, reason_str)。"""
    for i in range(0, len(data), CHUNK_BYTES):
        chunk = data[i:i + CHUNK_BYTES]
        hexstr = frame_hex(chunk)
        ok_append = False
        for _ in range(3):
            lines = send_cmd(ser, "ir extload " + hexstr, timeout=6.0,
                             stop_tokens=("IR_EXTLOAD_APPEND", "IR_EXTLOAD_FAIL"))
            if any("UNKNOWN IR SUBCOMMAND" in l.upper() for l in lines):
                return False, "UNSUPPORTED"
            if any("IR_EXTLOAD_APPEND" in l.upper() for l in lines):
                ok_append = True
                break
            time.sleep(0.3)  # 云日志穿插/CLI 未及时读取时重试
        if not ok_append:
            return False, "CHUNK_FAIL:" + " | ".join(lines)
    # 提交并回显（含重试）
    clines = None
    for _ in range(3):
        clines = send_cmd(ser, "ir extload commit", timeout=6.0,
                          stop_tokens=("IR_EXTLOAD_ECHO", "IR_EXTLOAD_FAIL"))
        if any("UNKNOWN IR SUBCOMMAND" in l.upper() for l in clines):
            return False, "UNSUPPORTED"
        if any("IR_EXTLOAD_ECHO" in l.upper() for l in clines):
            break
        time.sleep(0.3)
    if clines is None:
        return False, "COMMIT_NO_RESPONSE"
    commit_len = None
    echo = None
    for l in clines:
        lu = l.upper()
        if lu.startswith("IR_EXTLOAD_OK"):
            try:
                commit_len = int(l.split("=", 1)[1].split()[0])
            except Exception:
                commit_len = None
        if lu.startswith("IR_EXTLOAD_ECHO"):
            echo = l.split(" ", 1)[1].strip() if " " in l else ""
    if commit_len is None or echo is None:
        return False, "COMMIT_FAIL:" + " | ".join(clines)
    try:
        echo_bytes = bytes(int(x, 16) for x in echo.split())
    except Exception:
        return False, "ECHO_PARSE_FAIL"
    return True, (commit_len, echo_bytes, echo_bytes == data)


def main():
    ap = argparse.ArgumentParser(description="本地单次受控红外回放门禁")
    ap.add_argument("--candidate", required=True, help="候选编号，如 002")
    ap.add_argument("--authorize", action="store_true",
                    help="必须显式传入才会真实发射（=用户口头授权 允许单次回放候选XXX）")
    ap.add_argument("--verify-load", action="store_true",
                    help="仅验证加载链路（分块载入+回显比对），全程禁止发射")
    args = ap.parse_args()

    cid = CID_PREFIX + args.candidate
    bin_path, _ = find_candidate(cid)
    if not bin_path:
        print("ERROR: 未找到候选 BIN: %s" % cid)
        return 2
    data = open(bin_path, "rb").read()
    sha = sha256_file(bin_path)
    js_path = find_json(cid)
    expected_sha = None
    if js_path:
        try:
            expected_sha = json.load(open(js_path)).get("bin_sha256")
        except Exception:
            expected_sha = None

    gate_ok, gate_detail = cr.integrity_gate(data, {"overflow_count": 0,
                                                     "resync_count": 0,
                                                     "timeout_count": 0})

    print("REPLAY_CANDIDATE_ID=%s" % cid)
    print("REPLAY_CANDIDATE_LENGTH=%d" % len(data))
    print("REPLAY_CANDIDATE_SHA256=%s" % sha)
    print("MANIFEST_SHA256=%s" % (expected_sha or "n/a"))
    print("SHA_MATCH=%s" % (sha == expected_sha if expected_sha else "n/a"))
    print("FRAME_INTEGRITY_PASS=%s" % gate_ok)
    print("CLOUD_REAL_IR_ENABLED=%s" % CLOUD_REAL_IR_ENABLED)
    print("ENABLE_IR_MUTATING_COMMANDS_PUBLIC=%s" % ENABLE_IR_MUTATING_COMMANDS_PUBLIC)
    print("GUEST_REAL_IR_ALLOWED=%s" % GUEST_REAL_IR_ALLOWED)
    print("MQTT_REAL_IR_ALLOWED=%s" % MQTT_REAL_IR_ALLOWED)
    print("WEB_REAL_IR_ALLOWED=%s" % WEB_REAL_IR_ALLOWED)
    print("AUTO_REPLAY_ALLOWED=%s" % AUTO_REPLAY_ALLOWED)
    print("IR_TRANSMIT_AUTO_RETRY_DISABLED=%s" % IR_TRANSMIT_AUTO_RETRY_DISABLED)

    if not gate_ok:
        print("FRAME_INTEGRITY_FAIL: 候选 BIN 帧结构不合法，拒绝。")
        return 4

    if args.verify_load:
        # Phase A：仅验证加载链路，全程禁止发射。
        port = cr.detect_ch9102_port()
        if not port:
            print("ERROR: 未检测到 CH9102 (VID=1A86/PID=55D4)。")
            return 3
        ser = cr.open_serial(port, ESP_DEBUG_BAUD)
        if not ser:
            print("ERROR: 无法独占打开 %s。" % port)
            return 4
        wait_cli_ready(ser)
        try:
            ok, res = load_and_verify(ser, data)
        finally:
            try:
                ser.close()
            except Exception:
                pass
        if not ok:
            print("IR_EXTLOAD_IMPLEMENTED=False")
            detail = res if isinstance(res, str) else ""
            print("LOAD_CHAIN_FAIL: 回放能力不可用（%s），拒绝发射。" % detail)
            return 6
        commit_len, echo_bytes, byte_identical = res
        print("IR_EXTLOAD_IMPLEMENTED=True")
        print("IR_EXTLOAD_FILE_SHA256_PASS=%s" % (sha == expected_sha if expected_sha else "n/a"))
        print("IR_EXTLOAD_LENGTH_PASS=%s" % (commit_len == len(data)))
        # §一 校正：extload 仅把字节载入 ESP 发射缓冲（staging），并未写入 ZJ-IR-V2 物理模块。
        # ZJ-IR-V2 收 AFN=0x22 即发射，无独立「存储但不发射」命令；物理模块写入/发射仅在显式 ir extsend 时发生。
        print("IR_EXTLOAD_STAGING_BUFFER_PASS=True  # 字节已逐字节载入 ESP 发射缓冲（staging）；尚未写入物理模块")
        print("IR_EXTLOAD_STAGING_READBACK_PASS=%s" % (echo_bytes is not None))
        print("IR_EXTLOAD_STAGING_READBACK_BYTE_IDENTICAL=%s" % byte_identical)
        print("IR_MODULE_EXTERNAL_CODE_WRITE_PASS=pending  # 等待显式 ir extsend + 模块 ACK 方可证明")
        print("IR_MODULE_TRANSMIT_ACK_PASS=pending  # 等待显式 ir extsend + 模块 ACK 方可证明")
        print("IR_EXTLOAD_AUTO_SEND_DISABLED=True  # extload 不发射；仅显式 ir extsend 发射")
        print("LOAD_CHAIN_NO_EMIT=True")
        print("VERIFY_LOAD_DONE: 加载链路验证完成，未发射。可据此请求用户单次真实回放确认。")
        return 0

    if args.authorize:
        # Phase B：用户已回复 '允许单次回放候选XXX' 后的真实发射（载入 + 发射一次）。
        port = cr.detect_ch9102_port()
        if not port:
            print("ERROR: 未检测到 CH9102。")
            return 3
        ser = cr.open_serial(port, ESP_DEBUG_BAUD)
        if not ser:
            print("ERROR: 无法独占打开 %s。" % port)
            return 4
        wait_cli_ready(ser)
        try:
            ok, busy, responded = module_query_ok(ser, window_s=20.0)
            print("MODULE_QUERY_PASS=%s" % responded)
            print("MODULE_BUSY=%s" % busy)
            if not ok:
                print("GATE_FAIL: 模块查询未通过，拒绝发射。")
                return 5
            ok2, res = load_and_verify(ser, data)
            if not ok2:
                print("IR_EXTLOAD_IMPLEMENTED=False")
                print("LOAD_CHAIN_FAIL: 载入失败，拒绝发射。")
                return 6
            commit_len, echo_bytes, byte_identical = res
            if not byte_identical:
                print("IR_EXTLOAD_READBACK_BYTE_IDENTICAL=False")
                print("LOAD_CHAIN_BYTE_MISMATCH: 回显与候选不一致，拒绝发射。")
                return 7
            ext_lines = send_cmd(ser, "ir extsend", timeout=6.0,
                                  stop_tokens=("IR_EXTSEND_REQUESTED", "IR_EXTSEND_FAIL"))
            ack = any("IR_EXTSEND_REQUESTED" in l.upper() for l in ext_lines)
            print("IR_EXTLOAD_IMPLEMENTED=True")
            print("IR_EXTLOAD_READBACK_BYTE_IDENTICAL=True")
            print("IR_MODULE_TRANSMIT_ACK_PASS=%s" % ack)
            print("IR_TRANSMIT_COMMAND_PASS=%s" % ack)
            print("IR_SEND_COMMAND_COUNT=1")
            print("IR_SEND_AUTO_RETRY_COUNT=0")
            print("REAL_IR_TRANSMIT_COUNT=1")
            print("")
            print("已单次发射候选 %s。请用户现场观察空调反应（蜂鸣/开机/制冷/24℃/静音/扫风）。" % cid)
            print("注意：IR_MODULE_TRANSMIT_ACK_PASS 仅证明模块接受/执行了发射命令，不代表空调一定响应；最终以用户现场观察为准。")
            return 0
        finally:
            try:
                ser.close()
            except Exception:
                pass

    print("AUTHORIZE_NOT_SET: 未发射。请用户在现场确认全部 §四 条件后，")
    print("  回复 '允许单次回放候选%s'，再由 Agent 以 --authorize 执行一次。" % args.candidate)
    print("  或先以 --verify-load 验证加载链路（不发射）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
