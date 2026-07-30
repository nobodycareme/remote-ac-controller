# IR Simple Learner 使用说明

## 这是什么
一个最小Windows红外学习工具，用于配合ESP8266 NodeMCU + ZJ-IR-V2模块学习海信空调遥控器红外码。

## 环境要求
- Windows 10/11
- Python 3.9+ (含 pyserial)
- ESP8266 NodeMCU (CH9102 USB芯片)
- ZJ-IR-V2 红外学习模块
- 海信空调遥控器

## 使用步骤

### 1. 烧录固件
```powershell
cd <repo>\firmware
.\tools\dev.ps1 build -Profile ir-lab
.\tools\dev.ps1 upload -Profile ir-lab
```

**重要**: 烧录前确认 dev.ps1 使用的 Profile 支持 `ENABLE_IR_MUTATING_COMMANDS` 和 `ENABLE_IR_LAB_LEARNING_COMMANDS`。

### 2. 连接设备
NodeMCU 通过 USB 连接电脑。Windows 应自动识别为 CH9102 串口。

### 3. 启动工具
双击 `run_simple_ir_learner.bat`

### 4. 连接串口
- 点击 "Scan Ports" 自动搜索 CH9102
- 选择串口，点击 "Connect"

### 5. 选择空调状态
- 从预设下拉框选择一个状态（如"制冷24℃ 自动风"）
- 或手动填写状态名称和参数

### 6. 采集红外码
- 点击 "Capture 1"
- 界面显示 "please press remote" 后，**按一次遥控器**
- 等待保存完成
- 按相同步骤完成 Capture 2 和 Capture 3

### 7. 比较结果
- 点击 "Compare All"
- 查看三次采集的长度和SHA256
- 查看两两之间的字节差异

### 8. 选择 Canonical
- 在下拉框选择认为正确的一次（1、2或3）
- 点击 "Select Canonical"

### 9. 保存位置
所有学习结果保存在:
`<repo>\Private\Firmware\IR\Learned\`（可用环境变量 `IR_LEARNED_ROOT` 覆盖）

## 自测
```cmd
run_simple_ir_learner.bat --self-test
```

## 注意事项
- **学习工具不会自动发射红外**。保存的帧仅用于后续固件集成。
- **保存成功不等于空调已经物理响应**。需要单独验证。
- **三次采集不完全一致不一定失败**。空调遥控器帧可能含有变化字段（如时间）。
- **退出未确认时不能继续学习**。重新连接设备或重新上电后重试。

## 固件要求
ESP8266 固件必须:
1. 20H 进入学习等待模块 01H/status=0 确认
2. 21H 退出学习等待模块 01H/status=0 确认
3. 接收 22H 完整帧并通过 USB 串口传回 PC
4. 不自动回放或发射 22H 帧
