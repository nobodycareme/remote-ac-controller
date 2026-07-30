# IR Learning Studio

本工具是 Windows 本地运行的“空调红外学习工作台”。它只负责让 ESP8266 进入 ZJ-IR-V2 外部学习模式、接收 AFN=22H 学习帧、校验并保存到 `Private\Firmware\IR\Library`。它不会自动回放、不会自动 build、不会自动 flash。

启动：

```powershell
.\tools\dev.ps1 -Command ir-learning-studio
```

库校验：

```powershell
.\tools\dev.ps1 -Command ir-library-validate
```

生成待烧录固件输入：

```powershell
.\tools\dev.ps1 -Command ir-library-generate
```

生成命令只写入 gitignored 的 `src\private_ir_codes\generated\ir_library_generated.inc`，不会构建、烧录或发射红外。

## 操作流程

1. 扫描并连接 CH9102 设备，VID/PID 必须是 `1A86/55D4`。
2. 加载模板或新建状态，补全完整空调状态、遥控器屏幕显示和最终触发按键。
3. 保存草稿。
4. 点击“开始本次采集”。
5. 只有在界面提示后，才将原装遥控器对准红外学习模块并短按一次。
6. 默认重复采集 3 次。
7. 查看样本长度、SHA256 和差异摘要。
8. 样本一致时可推荐第 1 条，但仍必须人工点击批准。
9. 样本不一致时不会自动投票、拼接或修补；可以继续采集、标记 variant 或放弃。
10. 批准后再用 `ir-library-validate` 校验全库。

## 安全边界

- 学习台客户端会阻断 replay/send 类命令。
- 固件学习接口使用 `ir_learn_begin`、`ir_learn_export`、`ir_learn_cancel`、`ir_learn_clear`。
- 原始帧只通过 chunked Base64 export 返回，不在普通日志展示完整字节。
- 采集完成、超时、取消和关闭时都走退出学习流程，不回发 22H。
