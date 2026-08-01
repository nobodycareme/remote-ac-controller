**简体中文** | [English](../English/hardware-release-process.md)

# PCB 发布流程

本文档定义 PCB 制造数据的发布与校验流程。

## 修订模型

- 每个 PCB 修订号记录于 `hardware/pcb/REVISION`，变更历史见
  `hardware/pcb/CHANGELOG.md`。
- 修订号与软件版本（vX.Y.Z）相互独立。
- 制造数据更新（布局/制造文件变化）必须递增修订号。

## 制造包内容合同

制造包 `remote-ac-controller-pcb-rev1.0.1.zip` 只包含：

| ZIP 内路径 | 来源 |
|---|---|
| `gerber/`（8 个 Gerber 文件） | `hardware/pcb/fabrication/gerber/` |
| `drill/`（2 个钻孔文件） | `hardware/pcb/fabrication/drill/` |
| `test/FlyingProbeTesting.json` | `hardware/pcb/fabrication/test/` |
| `manufacturing-manifest.md` | `hardware/pcb/fabrication/` |
| `PCB下单必读.txt` | `hardware/pcb/fabrication/` |

EasyEDA 源文件（`source/Remote_AC_Controller_PCB_Rev1.0.1.eprj2`）保留在标签
源码树，**不属于**制造 ZIP 的默认内容。

## 打包与校验

- 使用 `tools/package-pcb-release.py --ref <tag> --out <目录>` 从 **Git 受控
  字节**（`git show <ref>:<path>`）打包，不受 Windows 换行设置影响。
- 同一 commit 两次打包 SHA256 必须一致（确定性）。
- 包内每个文件的大小与 SHA256 必须与 `manufacturing-manifest.md` 记录一致
  （`--verify` 自动核对）。
- 发布标签后，重新下载制造包并逐文件核对（不得使用打包前的本地文件代替）。

## 制造文件换行规则

- `hardware/pcb/fabrication/**` 与 `hardware/pcb/source/*.eprj2` 在
  `.gitattributes` 中标记为 `-text` / `binary`，禁止任何行尾转换。
- 哈希一律基于 Git blob 字节计算。

## 发布后错误处理

- 已发布制造资产不得静默替换。
- 若制造文件有误：递增 PCB 修订号（Rev x.y.z → Rev x.y.z+1），发布新补丁
  软件版本，并在旧 Release 正文加入中英文"已被取代"警告。
- Rev 1.0 制造文件已被 Rev 1.0.1 取代，不得用于制板。

## 禁止事项

- 制造包不得包含 BOM/坐标/私钥/数据库/真实红外帧或 `Private/` 内容。
- 不得把 EasyEDA 源文件当作制造包默认内容发布（除非显式决策）。

## 相关文档

- [制造清单](../../hardware/pcb/fabrication/manufacturing-manifest.md)
- English: [hardware-release-process](./hardware-release-process.md)、
  [versioning](./versioning.md)
