# Terry-CN

《全面战争：战锤 3》Assembly Kit 的 Terry 简体中文差分补丁。

当前交付：**2026-10-10 R3**，适用于 Assembly Kit **build 25616861 / Qt 5.12.0**。补丁校验原版文件，版本不匹配会停止安装。

## 使用

下载并完整解压 [Terry-CN-WH3-20261010-R3.zip](Terry-CN-WH3-20261010-R3.zip)，关闭 Terry 与 BOB，运行 `安装汉化.cmd`。安装不需要 Python；可用 `恢复英文.cmd` 恢复原版，用 `检查安装.cmd` 检查状态。

- [使用说明](使用说明.txt)：安装、升级、恢复及汉化范围。
- [验证说明](验证说明.txt)：实际测试结果和未覆盖边界。
- [ZIP SHA-256](Terry-CN-WH3-20261010-R3.zip.sha256)：整个交付包的校验值。

R3 词库共 2,266 条。内部标识、资源路径和存储值保留原样；部分动态技术信息仍可能显示英文。高级地形操作、外部工具链和全部导出流程尚未逐项实测。

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
- `working_data/Terry/status_tooltips.xml`

```powershell
python tools/build_patch.py --source backups/original-20261009 --output build/candidate
python tools/test_display_hooks.py
python tools/validate_patch.py build/candidate
```

安装回归测试读取根目录 `patch.json`，使用隔离的 `build/installer-tests/`；具体替换、测试和打包顺序见开发说明。根目录的差分与 ZIP 是已验证交付，候选构建不要未经检查覆盖它们。

`reports/` 内随仓库提交的记录属于 R3 的历史验证，不表示后续修改已经测试。只修改文档或项目规则时无需重建补丁。
