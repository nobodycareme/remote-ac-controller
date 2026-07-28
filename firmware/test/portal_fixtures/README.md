# Portal Detector 脱敏 HTML Fixtures (v0.3.4)

这些文件是 `PortalDetector::classifyResponse()` 离线单元测试（§一.6）使用的**脱敏**样本。
它们对应真实校园网在**未认证**时返回的拦截页形态，以及已联网/普通页面的形态。
所有内容均为公开信息（门户主机 `portal.campus.example.edu` 为学校公开域名），**不含**任何账号、密码、
MAC、Token 或个人数据。

| 文件 | 场景 | 期望 classify | 期望 AC_ID |
|------|------|---------------|-----------|
| `01_3xx_redirect.http` | 3xx 重定向到门户网管（Location 含 ac_id） | captive=YES | 8 |
| `02_200_autosubmit_form.html` | 200 透明拦截，含自动提交 form（action 指向 portal.campus.example.edu） | captive=YES | 8 |
| `02b_200_metarefresh_srunportal.html` | 200 透明拦截，含 meta-refresh 到 `srun_portal_pc?ac_id=8`（**真实校园形态**，body 无 portal.campus.example.edu 字面量） | captive=YES | 8 |
| `03_204_online.http` | 已联网（204 No Content） | captive=NO（已在线） | - |
| `04_plain_200.html` | 普通 200 页面（无校园网标记） | captive=NO | - |
| `05_network_failure.http` | 网络失败（GET 返回 <= 0） | captive=NO（未知） | - |

设备端 `PortalDetector::unitTest()` 内嵌了与上述文件等价的 fixture，运行 `nodemcuv2_portal_probe`
固件时随设备日志输出 `PORTAL_UNITTEST_PASS` / `PORTAL_UNITTEST_FAIL`。
