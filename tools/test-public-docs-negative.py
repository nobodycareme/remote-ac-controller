#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test-public-docs-negative.py — prove check-public-docs.py actually fails.

Each negative case copies the repository into a temp dir, applies ONE
sabotage, and asserts check-public-docs.py --root <temp> returns non-zero.
The real working tree is never modified.

Cases (section 9.3):
  1. put a Markdown link back inside the <p> nav block
  2. point the IR learning link to a non-existent #fragment
  3. call the public profile an "offline build"
  4. claim local-campus-example performs real authentication
  5. delete the desktop screenshot
  6. delete the mobile screenshot
  7. change the Chinese heading back to "Development and testing"
  8. add "连续 20 轮" (internal test language) to the README
  9. add a ../../docs image path back into the release notes
 10. make the CN/EN H2 structures inconsistent

Exit code non-zero if any negative case fails to fail.
"""
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHECKER = os.path.join(ROOT, "tools", "check-public-docs.py")


def build_temp_copy():
    tmp = tempfile.mkdtemp(prefix="pubdocs-neg-")
    for entry in os.listdir(ROOT):
        src = os.path.join(ROOT, entry)
        if entry in (".git", "node_modules", ".venv", "dist", "build"):
            continue
        dst = os.path.join(tmp, entry)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                ".git", "node_modules", ".venv", "dist", "build",
                "__pycache__", ".pio", ".build"))
        else:
            shutil.copy2(src, dst)
    return tmp


def run_checker(root_dir):
    r = subprocess.run([sys.executable, CHECKER, "--root", root_dir],
                       capture_output=True, text=True, timeout=180)
    return r.returncode


def case(no, name, sabotage, expect_fail=True):
    tmp = build_temp_copy()
    try:
        sabotage(tmp)
        rc = run_checker(tmp)
        if expect_fail:
            passed = rc != 0
        else:
            passed = rc == 0
        print(f"NEGATIVE_{no}_{name}_PASS={'True' if passed else 'False'} (rc={rc})")
        return passed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sabotage_1(root):
    # put a Markdown link back inside the HTML <p> nav block
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        '  <a href="#项目简介">项目简介</a>',
        '  [项目简介](#项目简介)')
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_2(root):
    # IR learning link points to a non-existent fragment
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "[红外学习工具](./docs/中文/红外学习.md)",
        "[红外学习工具](#红外学习工具)")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_3(root):
    # call the public profile an "offline build"
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "这是无凭据公开构建，不是完全离线构建",
        "这是一个完全离线的离线构建")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_4(root):
    # claim local-campus-example performs real authentication
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "只用于安全的公开编译验证",
        "启用了校园自动认证，填写 campus_secrets.h 后即可真实登录")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_5(root):
    p = os.path.join(root, "docs/assets/screenshots/dashboard-desktop.png")
    if os.path.exists(p):
        os.remove(p)


def sabotage_6(root):
    p = os.path.join(root, "docs/assets/screenshots/dashboard-mobile.png")
    if os.path.exists(p):
        os.remove(p)


def sabotage_7(root):
    # change the Chinese heading back to an English release heading
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("## 参与贡献与支持", "## Development and testing")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_8(root):
    # add internal test language to the README
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt += "\n稳定性：连续 20 轮测试全部通过。\n"
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_9(root):
    # add a ../../docs image path back into the release notes
    p = os.path.join(root, ".github/release-notes/v1.2.2.md")
    txt = open(p, encoding="utf-8").read()
    txt += '\n<img src="../../docs/assets/screenshots/dashboard-desktop.png" />\n'
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_10(root):
    # make the CN/EN H2 structures inconsistent (drop one EN heading)
    p = os.path.join(root, "README.en.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("## System layout", "## System layout (extra words)")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_11(root):
    # claim that cloud-enablement auto-connects at boot (v1.2.3 policy)
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "默认也不会在开机时自动连接网络",
        "Cloud 启用就会自动联网")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_12(root):
    # remove the empty-SSID hard guard from wifi_manager.cpp
    p = os.path.join(root, "firmware/shared/RemoteACCore/src/network/wifi_manager.cpp")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace('Serial.print(F("WIFI_CONNECT_SKIPPED source="));', "")
    txt = txt.replace('Serial.println(wifiPlanReasonLabel(out.reason));', "")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_13(root):
    # re-claim "deploy firmware only for phone control"
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "手机网页控制需要前端、后端、MQTT Broker 和 ESP8266 固件共同运行。",
        "只在家里用手机控制空调，可以只部署固件。")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_14(root):
    # re-claim an undocumented simulated device
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "云端后端、网页前端和固件可以分别启动和调试",
        "可以先用模拟设备体验网页控制")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_15(root):
    # re-claim any ESP8266 board runs the firmware unmodified
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "项目已在 NodeMCU ESP8266、DHT11 和 ZJ-IR-V2 上完成开发和验证。",
        "ESP8266 系列开发板配合支持红外发射的模块即可运行固件。")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_16(root):
    # re-claim components can be swapped freely
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "需要保持现有 API 与 MQTT 协议兼容。",
        "单独替换某一端不会影响其他部分。")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_17(root):
    # claim local-wifi-cloud needs no cloud credentials
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "该 Profile 会启用 `ENABLE_CLOUD_CREDENTIALS=1`",
        "local-wifi-cloud 无需 Cloud 凭据，只编译 Cloud 代码")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_18(root):
    # write the generic "编辑 globals.h" instead of the real file name
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("然后编辑 `Remote_AC_Controller.ino.globals.h`",
                      "然后编辑 `globals.h`")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_19(root):
    # campus guide: local-campus-example expands with AUTO_CAMPUS_AUTH=1
    p = os.path.join(root, "docs/中文/西电校园网自动认证.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "-DENABLE_AUTO_CAMPUS_AUTH=0 -DENABLE_CONTROLLED_LIVE_AUTH=0",
        "-DENABLE_AUTO_CAMPUS_AUTH=1 -DENABLE_CONTROLLED_LIVE_AUTH=0")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_20(root):
    # campus guide: restore an internal PASS field
    p = os.path.join(root, "docs/中文/西电校园网自动认证.md")
    txt = open(p, encoding="utf-8").read()
    txt += "\n核验状态：XIDIAN_PROFILE_PUBLIC_PARAMETERS_VERIFIED=True（只读复验）。\n"
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_21(root):
    # claim the public profile is fully offline / sensors only
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "这是无凭据公开构建，不是完全离线构建",
        "这是完全离线构建，public 只编译传感器")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_22(root):
    # re-claim that cloud_secrets.h existing means the config is usable
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "该 Profile 会启用 `ENABLE_CLOUD_CREDENTIALS=1`",
        "cloud_secrets.h 存在即代表可用，无需修改内容")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_23(root):
    # re-claim that `wifi connect <ssid>` still uses the local WPA password
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "临时切换到指定的开放 SSID；**不会**读取或使用 `wifi_secrets.h` 中的密码",
        "仍会使用 `wifi_secrets.h` 中的本地 WPA 密码连接")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_24(root):
    # delete the TLS material requirement (CA/fingerprint)
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "并且至少配置一个有效的 CA 证书或 TLS 指纹",
        "TLS 证书配置可留空")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_25(root):
    # re-allow the template broker host
    p = os.path.join(root, "docs/English/first-time-setup.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "the broker host must not be a template value such as `your-broker.example.com`",
        "the broker host may remain `your-broker.example.com`")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_26(root):
    # README claims the boot-time SSID can be empty and that is normal
    p = os.path.join(root, "README.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "默认也不会在开机时自动连接网络。",
        "开机时状态页可能不显示实际 SSID，这属于正常现象。")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_27(root):
    # CN/EN command semantics drift: EN no longer says the open SSID ignores
    # the local password (while CN does)
    p = os.path.join(root, "docs/English/first-time-setup.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "temporarily switch to the given open SSID; **does not** read or use the `wifi_secrets.h` password",
        "temporarily switch to the given open SSID using the local WPA password")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_28(root):
    # re-claim SSIDs cannot contain spaces
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "WiFi SSID 允许包含普通空格（例如 `Home WiFi`、`Lab Network 2`）",
        "WiFi SSID 不能包含空格，必须是一个连续字符串")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_29(root):
    # remove the 32-byte limit claim
    p = os.path.join(root, "docs/English/first-time-setup.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "its length is measured in UTF-8 bytes with a hard limit of 32 bytes",
        "there is no practical limit on SSID length")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_30(root):
    # claim the limit is 32 CHARACTERS (not bytes)
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("长度按 UTF-8 编码后的字节数计算，必须为 1 至 32 字节",
                      "长度按字符数计算，最多 32 个中文字符")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_31(root):
    # claim the fingerprint is filled but never applied at runtime
    p = os.path.join(root, "docs/English/first-time-setup.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "a SHA-1 server-certificate fingerprint (`setFingerprint`, 40 hex characters, colons optional) is used only when no valid CA is present",
        "a SHA-1 server-certificate fingerprint is stored for reference; it is not applied to the TLS client")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_32(root):
    # claim CA and fingerprint are BOTH used (double validation)
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "同时配置有效 CA 与有效指纹时只使用 CA（`setTrustAnchors`）",
        "同时配置有效 CA 与有效指纹时，两者会一起进行双重校验")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_33(root):
    # recommend setInsecure
    p = os.path.join(root, "docs/中文/首次配置.md")
    txt = open(p, encoding="utf-8").read()
    txt += "\n如果证书校验失败，可以在代码中调用 `setInsecure()` 关闭 TLS 校验继续连接。\n"
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_34(root):
    # claim the fingerprint never needs updating with the certificate
    p = os.path.join(root, "docs/English/first-time-setup.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace(
        "The fingerprint pins the current server certificate, so it must be updated when the certificate rotates.",
        "The fingerprint is permanent and never needs to change, regardless of certificate updates.")
    open(p, "w", encoding="utf-8").write(txt)


def sabotage_35(root):
    # CN/EN TLS priority mismatch: EN drops the CA-priority statement
    p = os.path.join(root, "docs/English/first-time-setup.md")
    txt = open(p, encoding="utf-8").read()
    txt = txt.replace("the **CA certificate takes priority**", "the fingerprint is always preferred")
    open(p, "w", encoding="utf-8").write(txt)


def main():
    results = [
        case(1, "markdown_in_html_block", sabotage_1),
        case(2, "broken_ir_fragment", sabotage_2),
        case(3, "false_offline_claim", sabotage_3),
        case(4, "campus_live_auth_claim", sabotage_4),
        case(5, "desktop_screenshot_deleted", sabotage_5),
        case(6, "mobile_screenshot_deleted", sabotage_6),
        case(7, "cn_english_heading", sabotage_7),
        case(8, "internal_test_language", sabotage_8),
        case(9, "release_image_path", sabotage_9),
        case(10, "h2_structure_drift", sabotage_10),
        case(11, "cloud_autoconnect_claim", sabotage_11),
        case(12, "empty_ssid_guard_removed", sabotage_12),
        case(13, "firmware_only_phone_control", sabotage_13),
        case(14, "undocumented_simulator", sabotage_14),
        case(15, "hardware_compat_overclaim", sabotage_15),
        case(16, "component_replacement_overclaim", sabotage_16),
        case(17, "lwc_no_cloud_creds", sabotage_17),
        case(18, "generic_globals_path", sabotage_18),
        case(19, "campus_example_auto_auth", sabotage_19),
        case(20, "campus_audit_field", sabotage_20),
        case(21, "public_fully_offline", sabotage_21),
        case(22, "cloud_exists_equals_valid", sabotage_22),
        case(23, "open_ssid_uses_local_password", sabotage_23),
        case(24, "tls_requirement_removed", sabotage_24),
        case(25, "template_broker_allowed", sabotage_25),
        case(26, "empty_status_is_normal", sabotage_26),
        case(27, "cmd_semantics_drift", sabotage_27),
        case(28, "ssid_no_space_claim", sabotage_28),
        case(29, "ssid_32byte_removed", sabotage_29),
        case(30, "ssid_32_characters_claim", sabotage_30),
        case(31, "fingerprint_not_applied", sabotage_31),
        case(32, "ca_fp_double_validation", sabotage_32),
        case(33, "set_insecure_recommended", sabotage_33),
        case(34, "fingerprint_no_rotation", sabotage_34),
        case(35, "cn_en_tls_priority_mismatch", sabotage_35),
    ]
    total = len(results)
    passed = sum(results)
    print(f"PUBLIC_DOC_NEGATIVE_TEST_TOTAL={total}")
    print(f"PUBLIC_DOC_NEGATIVE_TEST_PASS={passed}")
    if passed != total:
        print("PUBLIC_DOC_NEGATIVE_TEST_RESULT=FAIL")
        return 1
    print("PUBLIC_DOC_NEGATIVE_TEST_RESULT=PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
