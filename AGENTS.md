# Terry-CN 项目约定

本项目为《全面战争：战锤 3》Assembly Kit 的 Terry 制作简体中文差分补丁。目标是改善可见界面，同时保持原版编辑、资源处理、快捷键和工程存储行为；安装失败可回滚，用户可恢复英文。

## 协作与完成标准

- 用户要求修复、制作或修改时，完成范围内的实现、相应验证与交付；本地检查、候选构建和隔离测试可直接进行。只要求评审或诊断时先报告证据。
- 按任务需要读取下方资料，不为小改动遍历整个项目。缺少会影响正确性的信息时先完成不依赖该信息的工作，再说明最小缺口。
- 当前会话的明确授权持续有效。上传、发布、实机安装或清理已有授权时继续完成；授权范围不清时先把成果准备到可审查状态。不要为普通可逆修改增加逐步确认。
- 用中文说明结果，区分代码检查、自动测试、实际 Terry 操作与未测试内容。发现阻塞时给出具体失败和影响；验收通过后完成交付，不重复无关测试。

## 按任务取用

| 任务 | 入口 |
| --- | --- |
| 增补译文、统一术语 | `translations*.zh-CN.json`、`protected-identifiers.json`、`status-tooltips.zh-CN.json` |
| 修改差分与显示调用 | `tools/build_patch.py`、`tools/display_hooks.py`、`source-hashes.json` |
| 安装、升级、回滚 | `Install-TerryCN.ps1`、`tools/test_installer.py`、`tests/fixtures/` |
| 构建、适配和打包 | `开发说明.txt`、`requirements.txt`、`tools/package_release.py` |
| 玩家说明、兼容性和证据 | `使用说明.txt`、`验证说明.txt`、`reports/` 中与本次改动有关的报告 |

## 汉化与兼容性边界

- 优先在显示层转换文字。属性键、组件类型、枚举存储值、快捷键 ID、资源名、文件路径和用户输入保持原样；不为扩大汉化率修改地图格式、编辑算法或编译规则。
- 同一个英文词可能兼作界面标签与内部标识。直接替换字面量前确认具体调用点只用于显示，并维护 `protected-identifiers.json`；不要全局替换二进制字符串。
- 显示层按完整字符串匹配，未知内容透传。保留原参数、源字符串、Windows x64 ABI、Qt 字符串寿命、重定位和 ASLR。修改 `display_hooks.py` 或调用点后检查这些行为。
- 适配依据是 `source-hashes.json` 的原版文件。官方版本、Qt ABI 或哈希变化时重新审计；禁止跳过校验或仅改版本号来冒充兼容。
- 安装器保持四个明确目标、先完整预检再写入、验证原版备份、失败回滚。旧版汉化文件不能作为原版备份；扩大目标范围须有明确任务依据和相应验证。
- 词库和 JSON 使用 UTF-8；Windows PowerShell 5.1 使用的中文脚本保留 UTF-8 BOM。遵守 `.gitattributes`，交付文件的字节变化需要重新打包和校验。

## 构建与验证

开发使用 Windows x64 与可运行的 Python 3。依赖安装和原版基线准备见 `README.md`；不要把某台电脑的用户名、Steam 盘符或 Python 路径写成通用要求。

按改动选择检查：

| 改动 | 必要证据 |
| --- | --- |
| 仅文档、项目规则或 Git 配置 | 内容、命令、路径和差异检查；无需重跑二进制测试 |
| 词库、原生显示代码或二进制调用点 | 候选构建、原生显示测试、差分完整性；受影响界面的实机检查 |
| 安装器或交付差分 | 隔离目录的安装、恢复、升级及失败回滚测试 |
| 形成新的交付 ZIP | 与本次构建一致的验证记录、打包白名单、ZIP CRC、包内及整个 ZIP 的 SHA-256 |

候选构建的命令如下；输出目录已有需保留的结果时换用新的候选目录：

```powershell
python tools/build_patch.py --source backups/original-20261009 --output build/candidate
python tools/test_display_hooks.py
python tools/validate_patch.py build/candidate
```

验证器和安装测试目前使用 `backups/original-20261009`。安装测试读取根目录 `patch.json`：保留当前交付副本后，将已验证候选清单复制到根目录，再运行 `python tools/test_installer.py`。该测试写入独立的 `build/installer-tests/`，不写实际游戏目录；安装器仍会检查 Terry/BOB 进程，不绕过此检查。

实机验证使用独立测试工程，从受影响的菜单、对象或操作复现。涉及编辑与存储时核对属性值、快捷键，并进行中文保存与英文原版回读；只记录实际操作过的路径。保护用户未保存工作，不强杀编辑器；备份并恢复测试修改的个人配置。

自动检查通过不等于全功能实测。历史 `reports/` 是对应交付的证据，不可直接当作新修改的验证结果；新增失败、改动或明确疑点才扩大检查范围。

## 交付、Git 与清理

- 项目只维护汉化补丁。Git 跟踪源码、词库、差分、必要测试夹具、使用文档及经过检查的交付包；官方完整 DLL、原版备份、候选构建、依赖缓存和本机个人记录留在本地。
- 发布新补丁时同步清单版本、打包文件名、使用说明与验证记录，再运行 `python tools/package_release.py`。打包器拒绝覆盖同名 ZIP；先保留可恢复的上一版。单纯修改项目规则不重做已验证的补丁。
- Git 操作前核对目标仓库、分支与工作区；保留已有改动，不执行未经授权的强推或历史重写。上传后核对远端目标分支的提交和文件，不能用本地提交或其他分支的状态代替。
- 仓库使用用户确定的可见性；当前为私有。GitHub 源码上传、Release 附件和其他平台发布分别报告，不把其中一项当作全部完成。
- 清理已授权内容时移入 Windows 回收站并记录清单。先校验解析后的路径在指定目录内，保留原版基线和恢复所需文件；不清理游戏 Mod、用户地图或其他项目。

## 规则依据与维护

本文件参考 OpenAI 的 [GPT-6 提示指导](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#prompting-best-practices)、[GPT-6 的技能与项目规则建议](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)及 [AGENTS.md 文档](https://learn.chatgpt.com/docs/agent-configuration/agents-md)，于 2026-10-10 核对。

保留影响本项目结果的约束、入口和验收条件；详细流程放在对应文档中。实现变更时同步更新失效规则，不堆叠重复指令或把一次排查经历变成永久限制。
