# Terry-CN

《全面战争：战锤 3》Assembly Kit 的 Terry 简体中文差分补丁。

**创作者：Szy-Cathay**。本汉化补丁由 Codex（ChatGPT 6 Astra）完成。

当前交付：**v0.1.1（2026-10-14）**，适用于 Assembly Kit **build 25792521 / Qt 5.12.0**。补丁校验原版文件，版本不匹配会停止安装。

本版适配官方 2026-10-09 更新，重定位 40 处静态文字引用，保留完整词库和字体调整。用户已亲自安装验收，并明确确认中文保存后英文回读及属性值正常；记录区分人工反馈与自动测试。更新内容与证据见 [更新核查](更新核查-build25792521.txt)。本次完成本地交付，GitHub 提交、推送和公开发布尚未进行。

## 使用

使用 [Terry-CN-WH3-v0.1.1.zip](Terry-CN-WH3-v0.1.1.zip)，完整解压后，关闭 Terry 与 BOB，运行 `安装汉化.cmd`。安装不需要 Python；可用 `恢复英文.cmd` 恢复原版，用 `检查安装.cmd` 检查状态。已有 R2～R6 或 v0.1.0 时，先完成官方 Assembly Kit 更新，保留 `Terry-CN-backup`，再安装本版。新版安装器保留各版本原版备份，恢复得到当前上游原版。

- [使用说明](使用说明.txt)：安装、升级、恢复及汉化范围。
- [验证说明](验证说明.txt)：实际测试结果和未覆盖边界。
- [玩家发布说明](发布说明-v0.1.1.txt)：可直接转发给玩家，已包含在补丁 ZIP 中。
- [ZIP SHA-256](Terry-CN-WH3-v0.1.1.zip.sha256)：整个交付包的校验值。

本版将 Terry 顶部菜单、下拉菜单和工具栏文字改为 **微软雅黑 UI**。菜单 10 pt、文字图标 9 pt，扩展文字图标画布并调整菜单留白，改善原版 7 pt 位图文字对中文的可读性。字体使用系统已有字体，不额外分发字体文件；恢复英文时同时恢复原版字体与布局。

保留 R5 的全部汉化：词库 4,557 条，比 R4 新增 240 条，补齐 UTF-16 消息模板、动态错误说明、导入尺寸检查、自动保存恢复、工程验证、Houdini/Perforce 提示和撤销记录。208 处静态模板引用与 113 处 UTF-8 拼接片段在填入参数前翻译；补充 Qt 元对象翻译入口，使“撤销＋操作名称”等动态标题也能显示中文。

内部标识、资源路径、工程名称、动态参数和存储值保留原样。词库与调用点都有审计清单；实际操作和外部服务测试范围见验证说明。资源键、代码标识和用户输入中的英文不是汉化替换目标。

## 开发

项目规则见 [AGENTS.md](AGENTS.md)，详细构建说明见 [开发说明](开发说明.txt)。本仓库包含补丁源码、词库、差分、测试夹具及当前交付；不包含官方完整 DLL、本机原版备份或第三方依赖缓存。

在 Windows x64 安装 Python 3.8 或更高版本，安装与当前构建一致的依赖：

```powershell
python -m pip install --target tools/python-libs -r requirements.txt
```

从自己的官方 Assembly Kit **build 25792521** 准备下列**未汉化的原版文件**，按文件名放在 `backups/original-build-25792521/`，并核对 [source-hashes.json](source-hashes.json)：

- `binaries/tweak_terrainmetadataeditor.modder.x64.dll`
- `binaries/qttoolutility.modder.x64.dll`
- `binaries/Qt5Widgets.dll`
- `binaries/toolutilityqt.modder.x64.dll`
- `working_data/Terry/status_tooltips.xml`

```powershell
python tools/build_patch.py --source backups/original-build-25792521 --output build/candidate
python tools/test_display_hooks.py --qt-core "你的 Assembly Kit/binaries/Qt5Core.dll" --report build/candidate/reports/native-hook-tests.json
python tools/test_static_templates.py build/candidate --qt-core "你的 Assembly Kit/binaries/Qt5Core.dll" --report build/candidate/reports/static-template-tests.json
python tools/test_font_patch.py build/candidate --qt-bin "你的 Assembly Kit/binaries" --report build/candidate/reports/font-tests.json
python tools/validate_patch.py build/candidate --source backups/original-build-25792521 --report build/candidate/reports/patch-integrity-tests.json
```

安装回归测试通过 `--bundle` 选择含安装器和候选清单的目录，通过 `--source` 选择新版原版基线，使用隔离的 `build/installer-tests/`；准备步骤见开发说明。保留 `backups/original-20261009/` 作为旧版升级输入，其原版哈希由旧交付清单校验。根目录的差分、ZIP 与历史报告是已验证交付，候选测试通过 `--report` 另存记录。

`reports/` 内的自动验证记录绑定实际测试的差分或词库哈希。人工验收记录另注明反馈来源和范围，并绑定已验收候选与最终版相同的差分内容；未测量工程文件的逐字节一致性。打包器拒绝过期报告、未确认的回读或不一致的补丁内容。历史 v0.1.0/R6 记录不作为本版实机证据。

当前分支只保留 v0.1.1 ZIP 及其校验文件；旧包从 Git 历史按需临时取回用于回归测试。仓库保持公开，本次交付尚未上传或创建 GitHub Release。
