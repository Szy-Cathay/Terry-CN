# Terry-CN

《全面战争：战锤 3》Assembly Kit 的 Terry 简体中文差分补丁。

**创作者：Szy-Cathay**。本汉化补丁由 Codex（ChatGPT 6 Astra）完成。

当前版本：**v0.1.2（2026-10-22）**，适用于 Assembly Kit **build 25922678 / Qt 5.12.0**。严格校验原版文件，版本不匹配会停止安装。

本版适配上游变化，并收紧顶部工具栏间距。保留全部 4,557 条词库和微软雅黑 UI 字体，菜单仍为 10 pt、文字图标仍为 9 pt，高度不变。文字画布从 120×32 调为 112×32，按钮左右留白由各 5px 减至各 1px，按钮间距从 3px 减至 1px。

用户已安装 rc2，确认间距、字体和字号正常，并明确确认中文保存后英文回读与属性值正常。正式版与 rc2 仅清单版本字段不同，五个结果文件逐字节相同；**已装 rc2 无需重复安装**。人工反馈与自动检查分别记录，未测量场景文件逐字节一致性。

GitHub 发布入口：[v0.1.2](https://github.com/Szy-Cathay/Terry-CN/releases/tag/v0.1.2)，提供正式 ZIP 和 SHA-256 校验文件。适配与验收证据见 [更新核查](更新核查-build25922678.txt)。

## 使用

完整解压 [Terry-CN-WH3-v0.1.2.zip](Terry-CN-WH3-v0.1.2.zip)，保存工作并关闭 Terry 与 BOB，运行 `安装汉化.cmd`。安装无需 Python；`恢复英文.cmd` 恢复 build 25922678 英文原版，`检查安装.cmd` 检查状态。

已有 R2～R6、v0.1.0 或 v0.1.1 时，先通过 Steam 完成官方 Assembly Kit 更新，保留 `assembly_kit/Terry-CN-backup`。支持官方更新后残留旧 Qt/工具提示汉化的混合状态；新旧原版备份按各自哈希保留。rc1 可直接升级到正式版，rc2 无需重复安装。

- [使用说明](使用说明.txt)：安装、升级、恢复和汉化范围。
- [验证说明](验证说明.txt)：自动结果、用户验收及未覆盖边界。
- [发布说明](发布说明-v0.1.2.txt)：随 ZIP 提供的玩家说明。
- [ZIP SHA-256](Terry-CN-WH3-v0.1.2.zip.sha256)：整个交付包的校验值。

顶部菜单、下拉菜单和工具栏使用系统已有的微软雅黑 UI，不额外分发字体。恢复英文时同时恢复原版字体与布局。

保留 4,557 条显示词库、1,132 条独立字面量、15 条工具提示及 2,205 个显示/文字/字体调用点。208 处静态 Qt 模板引用与 113 处 UTF-8 拼接片段在填参前翻译，动态参数保留。本次重新审计并调整 41 处静态引用及 3 处片段引用；构建器另识别 2 处普通文字和 3 处显示调用移位。

内部标识、资源路径、工程名称、用户输入和存储值保持原样。显示层按完整字符串匹配，未知内容透传。覆盖范围与调用点计数不等于所有界面状态的汉化率或全功能实测。

## 开发

项目规则见 [AGENTS.md](AGENTS.md)，详细维护与回归准备见 [开发说明](开发说明.txt)。仓库包含源码、词库、差分、必要测试夹具及当前交付；不包含官方完整 DLL、本机原版备份或依赖缓存。

在 Windows x64 安装 Python 3.8 或更高版本，然后安装依赖：

```powershell
python -m pip install --target tools/python-libs -r requirements.txt
```

从官方 Assembly Kit **build 25922678** 准备下列未汉化原版文件，按文件名放入 `backups/original-build-25922678/`，并核对 [source-hashes.json](source-hashes.json)：

- `binaries/tweak_terrainmetadataeditor.modder.x64.dll`
- `binaries/qttoolutility.modder.x64.dll`
- `binaries/Qt5Widgets.dll`
- `binaries/toolutilityqt.modder.x64.dll`
- `working_data/Terry/status_tooltips.xml`

```powershell
python tools/build_patch.py --source backups/original-build-25922678 --output build/new-candidate --version v0.1.2
python tools/test_display_hooks.py --qt-core "你的 Assembly Kit/binaries/Qt5Core.dll" --report build/new-candidate/reports/native-hook-tests.json
python tools/test_static_templates.py build/new-candidate --qt-core "你的 Assembly Kit/binaries/Qt5Core.dll" --report build/new-candidate/reports/static-template-tests.json
python tools/test_font_patch.py build/new-candidate --qt-bin "你的 Assembly Kit/binaries" --report build/new-candidate/reports/font-tests.json
python tools/validate_patch.py build/new-candidate --source backups/original-build-25922678 --report build/new-candidate/reports/patch-integrity-tests.json
```

安装回归通过 `--bundle` 选择安装器和候选清单、`--source` 选择原版基线、`--report` 另存报告，只写独立的 `build/installer-tests/`。`--historical-dir` 指定旧 ZIP 及校验文件所在目录；`--previous-release-source` 指定 v0.1.1 的 build 25792521 原版，R2～v0.1.0 使用 `backups/original-20261009/`。旧包从 Git 历史取回并核对 SHA-256，不能省略升级检查。

同基线候选升级可通过构建器 `--previous-manifest` 继承已核实候选的补丁哈希，通过安装测试 `--previous-candidate` 验证。原版哈希不同的旧汉化仍被拒绝。已安装汉化时，字体测试可用 `--qt-widgets` 指向独立原版 Qt5Widgets，用 `--compare-build` 比较前一候选的真实 Qt 控件尺寸。

最终模板、字体、完整性及 36 项安装测试绑定 v0.1.2 清单；原生显示的 49,547 项记录来自同内容 rc2，最终词库哈希已再次核对。人工验收绑定相同补丁内容。打包器拒绝缺失、过期或不一致的报告和未确认的回读。

当前目录只保留 v0.1.2 正式 ZIP 及校验文件；旧版 ZIP 和收尾前快照保存在本地忽略目录，旧交付亦可从 Git 历史取回。GitHub 正式附件以 [v0.1.2 发布页](https://github.com/Szy-Cathay/Terry-CN/releases/tag/v0.1.2) 为准。
