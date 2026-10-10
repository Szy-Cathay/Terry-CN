param(
    [ValidateSet('Install', 'Restore', 'Check')][string]$Action = 'Install',
    [string]$AssemblyKitPath,
    [switch]$NoUi
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-BytesHash([byte[]]$Bytes) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($Bytes))).Replace('-', '') }
    finally { $algorithm.Dispose() }
}

function Get-AssemblyKit {
    if ($AssemblyKitPath) { $choices = @($AssemblyKitPath) }
    else {
        $steam = Get-ItemProperty -LiteralPath 'HKCU:\Software\Valve\Steam' -ErrorAction SilentlyContinue
        $steamRoots = @()
        if ($steam -and $steam.PSObject.Properties['SteamPath']) { $steamRoots += $steam.SteamPath }
        $steamRoots += @('E:\Steam', 'C:\Program Files (x86)\Steam')
        foreach ($root in @($steamRoots)) {
            $libraryFile = Join-Path $root 'steamapps\libraryfolders.vdf'
            if (Test-Path -LiteralPath $libraryFile) {
                foreach ($match in [regex]::Matches([IO.File]::ReadAllText($libraryFile), '"path"\s+"([^"]+)"')) {
                    $steamRoots += $match.Groups[1].Value.Replace('\\', '\')
                }
            }
        }
        $choices = @($steamRoots | Select-Object -Unique | ForEach-Object {
            Join-Path $_ 'steamapps\common\Total War WARHAMMER III\assembly_kit'
        })
    }
    foreach ($choice in $choices) {
        $candidate = [IO.Path]::GetFullPath($choice)
        if (Test-Path -LiteralPath (Join-Path $candidate 'assembly_kit\binaries\tweak.modder.x64.exe')) {
            $candidate = Join-Path $candidate 'assembly_kit'
        }
        if (Test-Path -LiteralPath (Join-Path $candidate 'binaries\tweak.modder.x64.exe')) { return $candidate }
    }
    if ($AssemblyKitPath -or $NoUi) { throw '找不到 Terry。请选择战锤 3 游戏目录或其中的 assembly_kit 文件夹。' }
    Add-Type -AssemblyName System.Windows.Forms
    $picker = New-Object Windows.Forms.FolderBrowserDialog
    $picker.Description = '请选择战锤 3 游戏目录或其中的 assembly_kit 文件夹'
    try {
        if ($picker.ShowDialog() -ne [Windows.Forms.DialogResult]::OK) { throw '已取消，未修改文件。' }
        $script:AssemblyKitPath = $picker.SelectedPath
        return Get-AssemblyKit
    } finally { $picker.Dispose() }
}

function Get-TargetPath([string]$Root, [string]$Relative) {
    if ([IO.Path]::IsPathRooted($Relative)) { throw '补丁包含无效路径。' }
    $target = [IO.Path]::GetFullPath((Join-Path $Root $Relative))
    if (-not $target.StartsWith($Root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw '补丁路径超出了 Assembly Kit 目录。'
    }
    return $target
}

function Get-PatchedBytes($Record, [byte[]]$Original) {
    if ($Record.PSObject.Properties['replacement']) {
        $result = [Convert]::FromBase64String($Record.replacement)
    } else {
        $result = New-Object byte[] $Record.patchedLength
        [Array]::Copy($Original, $result, $Original.Length)
        foreach ($edit in $Record.edits) {
            $before = [Convert]::FromBase64String($edit.before)
            $after = [Convert]::FromBase64String($edit.after)
            if ($before.Length -ne $after.Length -or $edit.offset -lt 0 -or $edit.offset + $before.Length -gt $Original.Length) {
                throw '补丁数据范围不正确。'
            }
            for ($index = 0; $index -lt $before.Length; $index++) {
                if ($Original[$edit.offset + $index] -ne $before[$index]) { throw '补丁内容与原文件不匹配。' }
            }
            [Array]::Copy($after, 0, $result, $edit.offset, $after.Length)
        }
        $tail = [Convert]::FromBase64String($Record.append)
        if ($Original.Length + $tail.Length -ne $result.Length) { throw '补丁文件长度不正确。' }
        [Array]::Copy($tail, 0, $result, $Original.Length, $tail.Length)
    }
    if ((Get-BytesHash $result) -ne $Record.patchedSha256) { throw '汉化结果校验失败，未写入程序。' }
    return ,$result
}

function Set-FileAtomic([string]$Target, [byte[]]$Bytes) {
    $temporary = $Target + '.terrycn-' + [Guid]::NewGuid().ToString('N') + '.tmp'
    try {
        [IO.File]::WriteAllBytes($temporary, $Bytes)
        [IO.File]::Replace($temporary, $Target, [System.Management.Automation.Language.NullString]::Value)
    } finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
    }
}

try {
    $kit = Get-AssemblyKit
    if (@(Get-Process -Name 'tweak.modder.x64', 'bob.modder.x64' -ErrorAction SilentlyContinue).Count -gt 0) {
        throw '请先关闭 Terry 和 BOB，再安装或恢复补丁。程序不会强制结束它们。'
    }
    $manifestPath = Join-Path $PSScriptRoot 'patch.json'
    $manifest = [IO.File]::ReadAllText($manifestPath) | ConvertFrom-Json
    $allowedPaths = @('binaries/tweak_terrainmetadataeditor.modder.x64.dll', 'binaries/qttoolutility.modder.x64.dll', 'binaries/Qt5Widgets.dll', 'binaries/toolutilityqt.modder.x64.dll', 'working_data/Terry/status_tooltips.xml')
    $actualPaths = @($manifest.files | ForEach-Object { $_.path })
    if ($manifest.format -ne 1 -or $actualPaths.Count -ne $allowedPaths.Count -or
        @(Compare-Object $actualPaths $allowedPaths).Count -ne 0) { throw '补丁清单格式不正确。' }
    $backupRoot = Join-Path $kit 'Terry-CN-backup'
    $operations = @()
    foreach ($record in $manifest.files) {
        $target = Get-TargetPath $kit $record.path
        if (-not [IO.File]::Exists($target)) { throw ('缺少程序文件：' + $record.path) }
        $current = [IO.File]::ReadAllBytes($target)
        $currentHash = Get-BytesHash $current
        $backupName = [IO.Path]::GetFileName($target) + '.' + $record.originalSha256.Substring(0, 16) + '.original'
        $backup = Join-Path $backupRoot $backupName
        $previousHashes = @()
        if ($record.PSObject.Properties['previousPatchedSha256']) { $previousHashes = @($record.previousPatchedSha256) }
        $isPreviousPatch = $previousHashes -contains $currentHash
        if ($currentHash -ne $record.originalSha256 -and $currentHash -ne $record.patchedSha256 -and -not $isPreviousPatch) {
            throw ('文件版本不匹配：' + $record.path + "`n可能是 Steam 已更新程序或安装了其他补丁。未覆盖任何文件。")
        }
        $alreadyDesired = ($Action -eq 'Install' -and $currentHash -eq $record.patchedSha256) -or
                          ($Action -eq 'Restore' -and $currentHash -eq $record.originalSha256)
        if ($Action -eq 'Check') {
            Write-Output ($record.path + ': ' + $(if ($currentHash -eq $record.patchedSha256) { '已安装本版汉化' } elseif ($isPreviousPatch) { '已安装可升级的旧版汉化' } else { '原版' }))
            continue
        }
        if ($alreadyDesired) {
            if ($Action -eq 'Install' -and (-not [IO.File]::Exists($backup) -or (Get-BytesHash ([IO.File]::ReadAllBytes($backup))) -ne $record.originalSha256)) {
                throw ('当前已是汉化文件，但缺少经过校验的原版备份：' + $record.path)
            }
            continue
        }
        if ($Action -eq 'Install') {
            $original = $current
            if ($isPreviousPatch) {
                if (-not [IO.File]::Exists($backup)) { throw ('升级需要原版备份：' + $record.path) }
                $original = [IO.File]::ReadAllBytes($backup)
                if ((Get-BytesHash $original) -ne $record.originalSha256) { throw ('升级所需原版备份校验失败：' + $record.path) }
            }
            $desired = Get-PatchedBytes $record $original
            if ([IO.File]::Exists($backup) -and (Get-BytesHash ([IO.File]::ReadAllBytes($backup))) -ne $record.originalSha256) {
                throw ('原版备份已被修改：' + $backup)
            }
        } else {
            if (-not [IO.File]::Exists($backup)) { throw ('找不到原版备份：' + $backup) }
            $desired = [IO.File]::ReadAllBytes($backup)
            if ((Get-BytesHash $desired) -ne $record.originalSha256) { throw ('原版备份校验失败：' + $backup) }
            $original = $desired
        }
        $operations += [pscustomobject]@{ Target=$target; Before=$current; After=$desired; Backup=$backup; Hash=$currentHash; OriginalHash=$record.originalSha256; Original=$original }
    }
    # Prepare every file and backup before changing any installed file.
    if ($Action -eq 'Install' -and $operations.Count -gt 0) {
        [IO.Directory]::CreateDirectory($backupRoot) | Out-Null
        foreach ($operation in $operations) {
            if (-not [IO.File]::Exists($operation.Backup)) { [IO.File]::WriteAllBytes($operation.Backup, $operation.Original) }
            if ((Get-BytesHash ([IO.File]::ReadAllBytes($operation.Backup))) -ne $operation.OriginalHash) { throw '原版备份校验失败。' }
        }
    }
    $applied = @()
    try {
        foreach ($operation in $operations) {
            if ((Get-BytesHash ([IO.File]::ReadAllBytes($operation.Target))) -ne $operation.Hash) {
                throw '程序文件在安装期间发生变化，已停止。'
            }
            Set-FileAtomic $operation.Target $operation.After
            $applied += $operation
            if ((Get-BytesHash ([IO.File]::ReadAllBytes($operation.Target))) -ne (Get-BytesHash $operation.After)) { throw '写入结果校验失败。' }
        }
    } catch {
        foreach ($operation in $applied) { Set-FileAtomic $operation.Target $operation.Before }
        throw
    }
    $message = switch ($Action) {
        'Install' { "Terry 界面汉化已安装。`n请照常从 Steam 启动 Battle Map Editor: Terry。`n`n恢复英文时双击《恢复英文.cmd》。`n原版备份保存在：$backupRoot" }
        'Restore' { '已恢复原版英文界面。原版备份仍保留。' }
        'Check' { '全部补丁目标文件的版本校验均通过。' }
    }
    Write-Output $message
    if (-not $NoUi) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($message, 'Terry 中文补丁', 'OK', 'Information') | Out-Null
    }
    exit 0
} catch {
    $message = $_.Exception.Message
    Write-Error $message -ErrorAction Continue
    if (-not $NoUi) {
        Add-Type -AssemblyName System.Windows.Forms
        [Windows.Forms.MessageBox]::Show($message, 'Terry 中文补丁：操作未完成', 'OK', 'Error') | Out-Null
    }
    exit 1
}
