# Terry-CN

《全面战争：战锤 3》Assembly Kit 的 Terry 简体中文差分补丁。

**创作者：Szy-Cathay、Codex（ChatGPT 6 Astra）**。本汉化补丁由 Codex 完成。

当前正式版：**v0.1.0（2026-10-10）**，适用于 Assembly Kit **build 25616861 / Qt 5.12.0**。补丁校验原版文件，版本不匹配会停止安装。

## 使用

从 [正式版本页面](https://github.com/Szy-Cathay/Terry-CN/releases/tag/v0.1.0) 下载，或使用仓库内的 [Terry-CN-WH3-v0.1.0.zip](Terry-CN-WH3-v0.1.0.zip)。完整解压后，关闭 Terry 与 BOB，运行 `安装汉化.cmd`。安装不需要 Python；可用 `恢复英文.cmd` 恢复原版，用 `检查安装.cmd` 检查状态。保留原版备份时，支持从 R2、R3、R4、R5、R6 直接安装正式版；R6 的汉化文件与正式版相同。

- [使用说明](使用说明.txt)：安装、升级、恢复及汉化范围。
- [验证说明](验证说明.txt)：实际测试结果和未覆盖边界。
- [玩家发布说明](发布说明-v0.1.0.txt)：可直接转发给玩家，已包含在补丁 ZIP 中。
- [ZIP SHA-256](Terry-CN-WH3-v0.1.0.zip.sha256)：整个交付包的校验值。

本版将 Terry 顶部菜单、下拉菜单和工具栏文字改为 **微软雅黑 UI**。菜单 10 pt、文字图标 9 pt，扩展文字图标画布并调整菜单留白，改善原版 7 pt 位图文字对中文的可读性。字体使用系统已有字体，不额外分发字体文件；恢复英文时同时恢复原版字体与布局。

保留 R5 的全部汉化：词库 4,557 条，比 R4 新增 240 条，补齐 UTF-16 消息模板、动态错误说明、导入尺寸检查、自动保存恢复、工程验证、Houdini/Perforce 提示和撤销记录。208 处静态模板引用与 113 处 UTF-8 拼接片段在填入参数前翻译；补充 Qt 元对象翻译入口，使“撤销＋操作名称”等动态标题也能显示中文。

内部标识、资源路径、工程名称、动态参数和存储值保留原样。词库与调用点都有审计清单；实际操作和外部服务测试范围见验证说明。资源键、代码标识和用户输入中的英文不是汉化替换目标。

## 开发

项目规则见 [AGENTS.md](AGENTS.md)，详细构建说明见 [开发说明](开发说明.txt)。本仓库包含补丁源码、词库、差分、测试夹具及当前交付；不包含官方完整 DLL、本机原版备份或第三方依赖缓存。

在 Windows x64 安装 Python 3.8 或更高版本，安装与当前构建一致的依赖：

```powershell
python -m pip install --target tools/python-libs -r requirements.txt
```

从自己的官方 Assembly Kit 准备下列**未汉化的原版文件**，按文件名放在 `backups/original-20261009/`，并核对 [source-hashes.json](source-hashes.json)：

- `binaries/tweak_terrainmetadataeditor.modder.x64.dll`
- `binaries/qttoolutility.modder.x64.dll`
- `binaries/Qt5Widgets.dll`
- `binaries/toolutilityqt.modder.x64.dll`
- `working_data/Terry/status_tooltips.xml`

```powershell
python tools/build_patch.py --source backups/original-20261009 --output build/candidate
python tools/test_display_hooks.py --qt-core "你的 Assembly Kit/binaries/Qt5Core.dll"
python tools/test_static_templates.py build/candidate --qt-core "你的 Assembly Kit/binaries/Qt5Core.dll"
python tools/test_font_patch.py build/candidate --qt-bin "你的 Assembly Kit/binaries"
python tools/validate_patch.py build/candidate
```

安装回归测试读取根目录 `patch.json`，使用隔离的 `build/installer-tests/`；具体替换、测试和打包顺序见开发说明。根目录的差分与 ZIP 是已验证交付，候选构建不要未经检查覆盖它们。

`reports/` 内的验证记录绑定实际测试的差分或词库哈希，不表示后续功能修改已经测试。v0.1.0 仅将已验证的 R6 更名为正式版；打包器核对除版本字段外的差分和安装工具逐字节一致，保留原测试记录及其原始哈希，并在交付报告中记录沿用关系。其他变更仍须提供对应的新验证结果。

当前分支只保留 v0.1.0 ZIP 及其校验文件；旧候选包从 Git 历史按需临时取回用于回归测试。仓库及 Release 已公开，玩家无需登录即可下载正式补丁。
