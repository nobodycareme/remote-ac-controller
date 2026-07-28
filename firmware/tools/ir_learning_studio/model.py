#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AC state schema, first-phase templates, and stable codeId generation."""

from __future__ import annotations

import getpass
import re
from copy import deepcopy
from typing import Dict, Iterable, List, Tuple

SCHEMA_VERSION = 1
MIN_CAPTURE_COUNT = 3
MAX_CAPTURE_COUNT = 5

POWER = ["on", "off"]
MODE = ["cool", "heat", "dry", "fan", "auto", "other"]
TEMPERATURES = [str(v) for v in range(16, 31)] + ["N/A"]
FAN_SPEED = ["silent", "low", "medium", "high", "turbo", "auto", "other"]
TRI_STATE = ["on", "off", "N/A"]
SWING = ["on", "off", "fixed", "unknown"]
TIMER = ["off", "configured", "N/A"]

STATE_FIELDS = [
    "power",
    "mode",
    "targetTemperatureC",
    "fanSpeed",
    "turboMode",
    "quietMode",
    "sleepMode",
    "ecoMode",
    "swingVertical",
    "swingHorizontal",
    "auxHeat",
    "displayLight",
    "timer",
]

REQUIRED_TOP_LEVEL = [
    "schemaVersion",
    "codeId",
    "displayName",
    "brand",
    "deviceModel",
    "remoteModel",
    "state",
    "remoteDisplayText",
    "triggerButton",
    "notes",
    "captureOperator",
    "status",
]

UNKNOWN_APPROVAL_FIELDS = ["swingVertical", "swingHorizontal"]
OPTIONAL_TOP_LEVEL = ["canonical", "physicalValidation", "unknownApprovalConfirmed", "templateNeedsUserCompletion"]


def default_definition() -> Dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "codeId": "",
        "displayName": "",
        "brand": "Hisense",
        "deviceModel": "",
        "remoteModel": "",
        "state": {
            "power": "on",
            "mode": "cool",
            "targetTemperatureC": "24",
            "fanSpeed": "auto",
            "turboMode": "off",
            "quietMode": "off",
            "sleepMode": "off",
            "ecoMode": "off",
            "swingVertical": "unknown",
            "swingHorizontal": "unknown",
            "auxHeat": "N/A",
            "displayLight": "N/A",
            "timer": "off",
        },
        "remoteDisplayText": "",
        "triggerButton": "",
        "notes": "",
        "captureOperator": getpass.getuser() or "local_user",
        "status": "draft",
    }


def normalize_for_display(definition: Dict) -> Dict:
    base = default_definition()
    merged = deepcopy(base)
    if isinstance(definition, dict):
        for key in REQUIRED_TOP_LEVEL:
            if key in definition and key != "state":
                merged[key] = definition[key]
        if isinstance(definition.get("state"), dict):
            merged["state"].update({k: definition["state"].get(k, merged["state"][k]) for k in STATE_FIELDS})
        for optional in OPTIONAL_TOP_LEVEL:
            if optional in definition:
                merged[optional] = definition[optional]
    return merged


def normalize_definition(definition: Dict) -> Dict:
    return normalize_for_display(definition)


def validate_code_id(code_id: str) -> Tuple[bool, str]:
    if not code_id:
        return False, "codeId is required"
    if not re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*_v[1-9][0-9]*", code_id):
        return False, "codeId must be lowercase ASCII snake_case and end with _vN"
    if any(x in code_id for x in ("/", "\\", "..", ":", " ")):
        return False, "codeId contains path or whitespace characters"
    return True, "ok"


def suggest_code_id(definition: Dict, version: int = 1) -> str:
    d = normalize_definition(definition)
    state = d["state"]
    brand = _token(d.get("brand") or "hisense")
    parts = [brand]
    if state["power"] == "off":
        parts.extend(["power", "off"])
    else:
        parts.append(_token(state["mode"]))
        if state["targetTemperatureC"] != "N/A":
            parts.append(str(state["targetTemperatureC"]))
        parts.extend(["fan", _token(state["fanSpeed"])])
        if state["turboMode"] == "on":
            parts.extend(["turbo", "on"])
        if state["quietMode"] == "on":
            parts.append("quiet")
        if state["sleepMode"] == "on":
            parts.append("sleep")
        parts.extend(["swing", "v", _token(state["swingVertical"])])
        parts.extend(["swing", "h", _token(state["swingHorizontal"])])
        parts.extend(["power", "on"])
    return "_".join(p for p in parts if p) + f"_v{int(version)}"


def validate_definition(definition: Dict, for_approval: bool = False, strict: bool = False) -> List[str]:
    d = deepcopy(definition) if strict and isinstance(definition, dict) else normalize_for_display(definition)
    errors: List[str] = []
    for key in REQUIRED_TOP_LEVEL:
        if not isinstance(d, dict) or key not in d:
            errors.append(f"missing top-level field: {key}")
    if errors and strict:
        return errors
    if strict:
        extras = sorted(set(d) - set(REQUIRED_TOP_LEVEL) - set(OPTIONAL_TOP_LEVEL))
        errors.extend([f"unexpected top-level field: {key}" for key in extras])
        if not isinstance(d.get("state"), dict):
            errors.append("state must be an object")
            return errors
        missing_state = [field for field in STATE_FIELDS if field not in d["state"]]
        errors.extend([f"missing state field: {field}" for field in missing_state])
        extras_state = sorted(set(d["state"]) - set(STATE_FIELDS))
        errors.extend([f"unexpected state field: {field}" for field in extras_state])
        if missing_state:
            return errors
    if d["schemaVersion"] != SCHEMA_VERSION:
        errors.append("unsupported schemaVersion")
    ok, msg = validate_code_id(d.get("codeId", ""))
    if not ok:
        errors.append(msg)
    if not str(d.get("displayName", "")).strip():
        errors.append("displayName is required")
    if not str(d.get("brand", "")).strip():
        errors.append("brand is required")

    state = d["state"]
    allowed = {
        "power": POWER,
        "mode": MODE,
        "targetTemperatureC": TEMPERATURES,
        "fanSpeed": FAN_SPEED,
        "turboMode": TRI_STATE,
        "quietMode": TRI_STATE,
        "sleepMode": TRI_STATE,
        "ecoMode": TRI_STATE,
        "swingVertical": SWING,
        "swingHorizontal": SWING,
        "auxHeat": TRI_STATE,
        "displayLight": TRI_STATE,
        "timer": TIMER,
    }
    for field, values in allowed.items():
        if state.get(field) not in values:
            errors.append(f"invalid state.{field}: {state.get(field)!r}")
    if state["mode"] == "fan" and state["targetTemperatureC"] != "N/A":
        errors.append("fan mode must use targetTemperatureC=N/A unless the remote display says otherwise")
    if state["sleepMode"] == "on":
        if state["mode"] in ("other", "auto") or state["targetTemperatureC"] == "N/A":
            errors.append("sleep mode must record a concrete base mode and temperature")
    if not str(d.get("remoteDisplayText", "")).strip():
        errors.append("remoteDisplayText is required")
    if not str(d.get("triggerButton", "")).strip():
        errors.append("triggerButton is required")
    if for_approval:
        unknown_fields = [field for field in UNKNOWN_APPROVAL_FIELDS if state.get(field) == "unknown"]
        if unknown_fields and d.get("unknownApprovalConfirmed") is not True:
            errors.append("unknown swing fields require explicit unknownApprovalConfirmed=true before approval")
    return errors


def validate_for_capture(definition: Dict, strict: bool = True) -> List[str]:
    return validate_definition(definition, for_approval=False, strict=strict)


def validate_for_approval(definition: Dict, strict: bool = True) -> List[str]:
    return validate_definition(definition, for_approval=True, strict=strict)


def is_complete_for_capture(definition: Dict) -> bool:
    return not validate_for_capture(definition, strict=True)


def first_phase_templates() -> List[Dict]:
    return [
        _template("关机", {"power": "off"}, "hisense_power_off_v1"),
        _template("制冷24℃，超强风速，上下扫风", {"mode": "cool", "targetTemperatureC": "24", "fanSpeed": "turbo", "swingVertical": "on"}),
        _template("制冷20℃，超强风速，上下扫风", {"mode": "cool", "targetTemperatureC": "20", "fanSpeed": "turbo", "swingVertical": "on"}),
        _template("制冷25℃，自动风", {"mode": "cool", "targetTemperatureC": "25", "fanSpeed": "auto"}),
        _template("制冷26℃，自动风", {"mode": "cool", "targetTemperatureC": "26", "fanSpeed": "auto"}),
        _template("制冷27℃，自动风", {"mode": "cool", "targetTemperatureC": "27", "fanSpeed": "auto"}),
        _template("制冷28℃，自动风", {"mode": "cool", "targetTemperatureC": "28", "fanSpeed": "auto"}),
        _template("制冷24℃，强力风", {"mode": "cool", "targetTemperatureC": "24", "turboMode": "on"}),
        _template("制冷24℃，上下扫风", {"mode": "cool", "targetTemperatureC": "24", "swingVertical": "on"}),
        _template("制冷24℃，左右扫风", {"mode": "cool", "targetTemperatureC": "24", "swingHorizontal": "on"}),
        _template("除湿24℃", {"mode": "dry", "targetTemperatureC": "24"}),
        _template("送风模式", {"mode": "fan", "targetTemperatureC": "N/A"}),
        _template("制热24℃", {"mode": "heat", "targetTemperatureC": "24"}),
        _template("制热26℃", {"mode": "heat", "targetTemperatureC": "26"}),
        _template("睡眠模式", {"sleepMode": "on"}),
    ]


def _template(display_name: str, state_updates: Dict, code_id: str = "") -> Dict:
    d = default_definition()
    d["displayName"] = display_name
    d["state"].update(state_updates)
    d["codeId"] = code_id or suggest_code_id(d)
    d["remoteDisplayText"] = ""
    d["triggerButton"] = ""
    d["notes"] = "待用户补全：左右扫风、上下扫风、静音、强力、基础风速、屏幕显示和最终触发按键。"
    d["templateNeedsUserCompletion"] = True
    return d


def _token(text: object) -> str:
    token = str(text or "").strip().lower()
    token = token.replace("+", "plus").replace("-", "_")
    token = re.sub(r"[^a-z0-9]+", "_", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token or "unknown"


def required_field_options() -> Dict[str, Iterable[str]]:
    return {
        "power": POWER,
        "mode": MODE,
        "targetTemperatureC": TEMPERATURES,
        "fanSpeed": FAN_SPEED,
        "turboMode": TRI_STATE,
        "quietMode": TRI_STATE,
        "sleepMode": TRI_STATE,
        "ecoMode": TRI_STATE,
        "swingVertical": SWING,
        "swingHorizontal": SWING,
        "auxHeat": TRI_STATE,
        "displayLight": TRI_STATE,
        "timer": TIMER,
    }
