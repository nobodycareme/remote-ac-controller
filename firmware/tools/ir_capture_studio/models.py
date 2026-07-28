#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
models.py — 红外学习采集台 数据模型与命名工具

只定义数据结构和纯函数，不依赖 GUI / 串口 / pyserial。
所有状态取值严格对照需求文档第七节。
"""

import re
import datetime

SCHEMA_VERSION = "1.0.0"
MODULE_MODEL = "ZJ-IR-V2"
IR_MODULE_BAUD = 19200          # ZJ-IR-V2 模块自身 UART 波特率（GUI 显示用）
ESP_CLI_BAUD = 115200           # ESP8266 调试/CLI 串口连接波特率（CH9102 直连 PC）
CH9102_VID = 0x1A86
CH9102_PID = 0x55D4

# ---------------- 空调状态枚举（第七节）----------------
MODES = ["off", "auto", "cool", "heat", "dry", "fan", "unknown", "custom"]
FANS = ["auto", "quiet", "low", "medium", "high", "turbo", "unknown", "custom"]
SWINGS = ["off", "on", "auto", "fixed", "unknown"]
ONOFF_UNK = ["off", "on", "unknown"]
POWER_AFTER = ["off", "on", "unchanged", "unknown"]
TEMPERATURES = [str(t) for t in range(16, 31)]  # "16".."30"
TEMP_SPECIAL = ["N/A", "unknown"]

# ---------------- 任务类型（第六节）----------------
TASK_TYPE_LABELS = [
    "开机", "关机", "设置完整状态", "温度升高", "温度降低", "设置指定温度",
    "模式切换", "风速切换", "设置指定风速", "上下扫风切换", "左右扫风切换",
    "静音切换", "强力模式切换", "睡眠模式切换", "自定义按键或状态",
]
TASK_CODE = {
    "开机": "POWER_ON", "关机": "POWER_OFF", "设置完整状态": "STATE_SET",
    "温度升高": "TEMP_UP", "温度降低": "TEMP_DOWN", "设置指定温度": "SET_TEMP",
    "模式切换": "MODE_CHANGE", "风速切换": "FAN_CHANGE", "设置指定风速": "SET_FAN",
    "上下扫风切换": "SV_TOGGLE", "左右扫风切换": "SH_TOGGLE", "静音切换": "QT_TOGGLE",
    "强力模式切换": "TB_TOGGLE", "睡眠模式切换": "SL_TOGGLE",
    "自定义按键或状态": "CUSTOM",
}

# ---------------- 失败类型（第二十三节）----------------
FAILURE_TYPES = [
    "serial_not_found", "serial_busy", "module_query_timeout", "module_busy",
    "learn_command_not_acknowledged", "timeout_waiting_remote", "invalid_frame_header",
    "invalid_length", "checksum_failure", "invalid_frame_tail", "payload_too_large",
    "uart_overflow", "partial_frame", "file_write_failure", "manifest_write_failure",
    "ambiguous_result", "user_cancelled",
]

# ---------------- 默认状态 ----------------
DEFAULT_STATE = {
    "power": "off",
    "mode": "cool",
    "temperatureC": "24",
    "fan": "quiet",
    "swingVertical": "on",
    "swingHorizontal": "on",
    "quiet": "off",
    "turbo": "off",
    "sleep": "off",
}

# ---------------- 预设（第八节）----------------
PRESETS = {
    "preset1": {  # 海信 / 制冷 / 24℃ / 静音 / 上下扫风开 / 左右扫风开
        "brand": "海信", "acModel": "", "remoteModel": "",
        "taskType": "设置完整状态",
        "stateBefore": {"power": "on", "mode": "cool", "temperatureC": "24",
                         "fan": "quiet", "swingVertical": "on", "swingHorizontal": "on",
                         "quiet": "off", "turbo": "off", "sleep": "off"},
        "stateAfter": {"power": "on", "mode": "cool", "temperatureC": "24",
                       "fan": "quiet", "swingVertical": "on", "swingHorizontal": "on",
                       "quiet": "off", "turbo": "off", "sleep": "off"},
        "buttonPressed": "状态键", "customTaskName": "", "captureCount": 3,
    },
    "preset2": {  # 关机
        "brand": "海信", "acModel": "", "remoteModel": "",
        "taskType": "关机",
        "stateBefore": {"power": "on", "mode": "cool", "temperatureC": "24",
                        "fan": "quiet", "swingVertical": "on", "swingHorizontal": "on",
                        "quiet": "off", "turbo": "off", "sleep": "off"},
        "stateAfter": {"power": "off", "mode": "cool", "temperatureC": "24",
                       "fan": "quiet", "swingVertical": "on", "swingHorizontal": "on",
                       "quiet": "off", "turbo": "off", "sleep": "off"},
        "buttonPressed": "电源键", "customTaskName": "", "captureCount": 3,
    },
    "preset3": {  # 制冷模式温度采集
        "brand": "海信", "acModel": "", "remoteModel": "",
        "taskType": "设置指定温度",
        "stateBefore": {"power": "on", "mode": "cool", "temperatureC": "24",
                        "fan": "quiet", "swingVertical": "on", "swingHorizontal": "on",
                        "quiet": "off", "turbo": "off", "sleep": "off"},
        "stateAfter": {"power": "on", "mode": "cool", "temperatureC": "24",
                       "fan": "quiet", "swingVertical": "on", "swingHorizontal": "on",
                       "quiet": "off", "turbo": "off", "sleep": "off"},
        "buttonPressed": "温度+/-键", "customTaskName": "", "captureCount": 3,
    },
    "preset4": {  # 自定义（全默认）
        "brand": "海信", "acModel": "", "remoteModel": "",
        "taskType": "自定义按键或状态",
        "stateBefore": dict(DEFAULT_STATE), "stateAfter": dict(DEFAULT_STATE),
        "buttonPressed": "", "customTaskName": "", "captureCount": 3,
    },
}


# 常见品牌中文 -> ASCII（用于文件名/会话目录，避免中文进入 BIN 文件名）
BRAND_MAP = {
    "海信": "HISENSE", "格力": "GREE", "美的": "MIDEA", "海尔": "HAIER",
    "松下": "PANASONIC", "大金": "DAIKIN", "三菱": "MITSUBISHI", "奥克斯": "AUX",
    "TCL": "TCL", "志高": "CHIGO", "小米": "XIAOMI", "长虹": "CHANGHONG",
    "科龙": "KELON", "惠而浦": "WHIRLPOOL", "格兰仕": "GALANZ",
}


def _ascii_only(s):
    """仅保留英文字母/数字/下划线/连字符，其余替换为下划线。"""
    if s is None:
        return ""
    s = str(s).strip().replace(" ", "_")
    s = re.sub(r"[^A-Za-z0-9_-]", "_", s)
    return s


def _brand_token(brand):
    b = (brand or "").strip()
    if b in BRAND_MAP:
        return BRAND_MAP[b]
    a = _ascii_only(b).upper()
    return a if a else "AC"


def _temp_token(t):
    if t in (None, "", "unknown", "N/A"):
        return None
    return "%sC" % str(t)


def _sv_token(v):
    return {"on": "SV_ON", "off": "SV_OFF", "auto": "SV_AUTO",
            "fixed": "SV_FIXED"}.get(v)


def _sh_token(v):
    return {"on": "SH_ON", "off": "SH_OFF", "auto": "SH_AUTO",
            "fixed": "SH_FIXED"}.get(v)


def _mode_token(m):
    if not m or m in ("unknown",):
        return None
    return str(m).upper()


def build_state_part(state):
    """根据按键前完整状态构造文件名状态段（ASCII）。"""
    parts = []
    mt = _mode_token(state.get("mode"))
    if mt:
        parts.append(mt)
    tt = _temp_token(state.get("temperatureC"))
    if tt:
        parts.append(tt)
    fan = state.get("fan")
    if fan and fan not in ("unknown",):
        parts.append(str(fan).upper())
    sv = _sv_token(state.get("swingVertical"))
    if sv:
        parts.append(sv)
    sh = _sh_token(state.get("swingHorizontal"))
    if sh:
        parts.append(sh)
    if state.get("quiet") == "on":
        parts.append("QT_ON")
    if state.get("turbo") == "on":
        parts.append("TB_ON")
    if state.get("sleep") == "on":
        parts.append("SL_ON")
    return "_".join(parts)


def build_task_part(task_type, state_before, state_after, custom_name):
    """根据任务类型与前后状态构造文件名词义段（ASCII）。"""
    code = TASK_CODE.get(task_type, "CUSTOM")
    if task_type == "温度升高":
        a = _temp_token(state_after.get("temperatureC"))
        return "TO_%s_%s" % (a or "X", code) if a else code
    if task_type == "温度降低":
        a = _temp_token(state_after.get("temperatureC"))
        return "TO_%s_%s" % (a or "X", code) if a else code
    if task_type == "设置指定温度":
        a = _temp_token(state_after.get("temperatureC"))
        return "%s_%s" % (a or "SET", code) if a else code
    if task_type == "模式切换":
        f = _mode_token(state_before.get("mode"))
        t = _mode_token(state_after.get("mode"))
        if f and t:
            return "%s_TO_%s_%s" % (f, t, code)
        return code
    if task_type == "风速切换":
        f = state_before.get("fan")
        t = state_after.get("fan")
        if f and t and f != "unknown" and t != "unknown":
            return "%s_TO_%s_%s" % (str(f).upper(), str(t).upper(), code)
        return code
    if task_type == "设置指定风速":
        f = state_after.get("fan")
        if f and f != "unknown":
            return "FAN_%s" % str(f).upper()
        return code
    if task_type == "自定义按键或状态":
        cn = _ascii_only(custom_name)
        return "CUSTOM_%s" % cn if cn else "CUSTOM"
    return code


def build_capture_filename(brand, state_before, state_after, task_type,
                           custom_name, sample_number):
    """构造 capture_NNN.bin 前缀（不含扩展名）。例：HISENSE_COOL_24C_QUIET_SV_ON_SH_ON_POWER_ON_001"""
    parts = [_brand_token(brand)]
    sp = build_state_part(state_before)
    if sp:
        parts.append(sp)
    tp = build_task_part(task_type, state_before, state_after, custom_name)
    if tp:
        parts.append(tp)
    name = "_".join(parts).strip("_")
    name = re.sub(r"_+", "_", name)
    name = "%s_%03d" % (name, int(sample_number))
    return name


def build_session_id(brand, state_before, state_after, task_type, custom_name,
                     when=None):
    """会话目录名：YYYYMMDD_HHMMSS_BRAND_MODE_TASKSHORT"""
    when = when or datetime.datetime.now()
    ts = when.strftime("%Y%m%d_%H%M%S")
    brand_tok = _brand_token(brand)
    mode_tok = _mode_token(state_before.get("mode")) or "X"
    task_tok = TASK_CODE.get(task_type, "CUSTOM")
    return "%s_%s_%s_%s_%s" % (ts, brand_tok, mode_tok, task_tok, brand_tok)


def normalize_state(d):
    """合并默认值，保证所有字段存在。"""
    s = dict(DEFAULT_STATE)
    if isinstance(d, dict):
        s.update({k: d.get(k, v) for k, v in DEFAULT_STATE.items()})
    return s


def build_sample_record_base(task):
    """
    构造样本 JSON 的基础字段骨架（第二节/二十二节）。
    task 为字典，含 brand/acModel/remoteModel/taskType/customTaskName/
    buttonPressed/notes/stateBefore/stateAfter/captureCount 等。
    返回可被 capture_core_adapter / storage 进一步补全的字典。
    """
    sb = normalize_state(task.get("stateBefore"))
    sa = normalize_state(task.get("stateAfter"))
    rec = {
        "schemaVersion": SCHEMA_VERSION,
        "sessionId": task.get("sessionId", ""),
        "captureId": "",
        "sampleNumber": task.get("sampleNumber", 1),
        "attemptNumber": task.get("attemptNumber", 1),
        "captureTime": "",
        "brand": task.get("brand", ""),
        "acModel": task.get("acModel", ""),
        "remoteModel": task.get("remoteModel", ""),
        "taskType": task.get("taskType", "自定义按键或状态"),
        "customTaskName": task.get("customTaskName", ""),
        "buttonPressed": task.get("buttonPressed", ""),
        "stateBefore": sb,
        "stateAfter": sa,
        "userNotes": task.get("notes", ""),
        "moduleModel": MODULE_MODEL,
        "moduleUartBaud": IR_MODULE_BAUD,
        "serialPort": task.get("serialPort", ""),
        "firmwareSha256": task.get("firmwareSha256", "unknown"),
        "learnCommand": "ir extlearn",
        "learnTimeoutSeconds": task.get("learnTimeoutSeconds", 30),
        "moduleAckReceived": None,
        "learnResultReceived": None,
        "AFN": None,
        "externalCodeLength": None,
        "checksumExpected": None,
        "checksumActual": None,
        "checksumPass": None,
        "frameHeaderPass": None,
        "frameTailPass": None,
        "binLengthMatch": None,
        "uartTimeoutCount": 0,
        "uartChecksumFailureCount": 0,
        "uartOverflowCount": 0,
        "uartResyncCount": 0,
        "clickTimestamp": task.get("clickTimestamp"),
        "commandSentTimestamp": None,
        "learningConfirmedTimestamp": None,
        "localPromptTimestamp": None,
        "captureCompleteTimestamp": None,
        "commandToPromptMs": None,
        "captureDurationMs": None,
        "captureResult": "pending",
        "failureReason": None,
        "ambiguousResult": False,
        "replayed": False,
        "cloudTriggered": False,
        "binSha256": None,
        "jsonSha256": None,
        "txtSha256": None,
    }
    return rec


def now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
