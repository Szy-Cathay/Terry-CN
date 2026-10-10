import hashlib
import json
import shutil
import subprocess
import base64
import zipfile
import ctypes as c
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT / 'patch.json').read_text(encoding='utf-8'))
kit = ROOT / 'build' / 'installer-tests' / datetime.now().strftime('%Y%m%d-%H%M%S') / '中文路径 有空格' / 'assembly_kit'
assert not kit.exists(), 'Use a fresh isolated test directory'
kit.mkdir(parents=True)
for record in manifest['files']:
    target = kit / record['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'backups/original-20261009' / target.name, target)
(kit / 'binaries/tweak.modder.x64.exe').write_bytes(b'Isolated installer test fixture')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def hashes():
    return {r['path']: sha(kit / r['path']) for r in manifest['files']}

results = []
def run(action, success=True):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(ROOT / 'Install-TerryCN.ps1'), '-Action', action,
                             '-AssemblyKitPath', str(kit), '-NoUi'], capture_output=True)
    assert (result.returncode == 0) == success, (action, result.returncode, result.stdout, result.stderr)
    return result.returncode

expected_original = {r['path']: r['originalSha256'] for r in manifest['files']}
expected_patched = {r['path']: r['patchedSha256'] for r in manifest['files']}
run('Install')
assert hashes() == expected_patched
results.append('Install: all target hashes match')
run('Install')
assert hashes() == expected_patched
results.append('Repeated install: unchanged')
run('Check')
results.append('Check: accepts patched files')
run('Restore')
assert hashes() == expected_original
results.append('Restore: all original hashes match')
run('Restore')
assert hashes() == expected_original
results.append('Repeated restore: unchanged')
last = kit / manifest['files'][-1]['path']
good = last.read_bytes()
last.write_bytes(good + b'changed version')
before = hashes()
run('Install', False)
assert hashes() == before
results.append('Version mismatch in last file: rejects before any target write')
last.write_bytes(good)
backup = next((kit / 'Terry-CN-backup').glob('*xml*.original'))
backup_original = backup.read_bytes()
backup.write_bytes(b'damaged')
before = hashes()
run('Install', False)
assert hashes() == before
results.append('Damaged original backup: rejects before any target write')
backup.write_bytes(backup_original)
run('Install')
backup.write_bytes(b'damaged')
before = hashes()
run('Restore', False)
assert hashes() == before
results.append('Damaged restore backup: rejects before any target write')
backup.write_bytes(backup_original)
run('Restore')
assert hashes() == expected_original
assert not list(kit.rglob('*.tmp'))
results.append('No temporary target files remain')

# Real R2 inputs with verified original backups, then upgrade and restore.
previous = json.loads((ROOT / 'tests/fixtures/patch-r2.json').read_text(encoding='utf-8'))
for record in previous['files']:
    target = kit / record['path']
    data = bytearray(target.read_bytes())
    if 'replacement' in record:
        data = base64.b64decode(record['replacement'])
    else:
        for edit in record['edits']:
            after = base64.b64decode(edit['after'])
            data[edit['offset']:edit['offset'] + len(after)] = after
        data.extend(base64.b64decode(record['append']))
    target.write_bytes(data)
    assert sha(target) == record['patchedSha256']
old_hashes = hashes()
backup_original = backup.read_bytes()
backup.unlink()
run('Install', False)
assert hashes() == old_hashes
results.append('R2 upgrade without original backup: all targets unchanged')
backup.write_bytes(backup_original)
run('Install')
assert hashes() == expected_patched
results.append('Direct R2 upgrade: all target hashes match')
run('Restore')
assert hashes() == expected_original
results.append('Restore after R2 upgrade: exact originals')

# Also exercise the immediately preceding publicized delivery, whose Qt file
# and display hooks differ from R2. Its archive remains recoverable in Git.
for version in ['R3', 'R4']:
    with zipfile.ZipFile(ROOT / f'Terry-CN-WH3-20261010-{version}.zip') as archive:
        previous = json.loads(archive.read('patch.json'))
    for record in previous['files']:
        target = kit / record['path']
        data = bytearray(target.read_bytes())
        if 'replacement' in record:
            data = base64.b64decode(record['replacement'])
        else:
            for edit in record['edits']:
                before, after = (base64.b64decode(edit[key]) for key in ['before', 'after'])
                assert data[edit['offset']:edit['offset'] + len(before)] == before
                data[edit['offset']:edit['offset'] + len(after)] = after
            data.extend(base64.b64decode(record['append']))
        target.write_bytes(data)
        assert sha(target) == record['patchedSha256']
    run('Install')
    assert hashes() == expected_patched
    results.append(f'Direct {version} upgrade: all target hashes match')
    run('Restore')
    assert hashes() == expected_original
    results.append(f'Restore after {version} upgrade: exact originals')

# Allow reading file 2 but deny replacement: file 1 must roll back after failure.
k = c.WinDLL('kernel32', use_last_error=True)
k.CreateFileW.argtypes = [c.c_wchar_p, c.c_uint32, c.c_uint32, c.c_void_p, c.c_uint32, c.c_uint32, c.c_void_p]
k.CreateFileW.restype = c.c_void_p
k.CloseHandle.argtypes = [c.c_void_p]
handle = k.CreateFileW(str(kit / manifest['files'][1]['path']), 0x80000000, 1, None, 3, 0, None)
assert handle not in (None, c.c_void_p(-1).value)
try:
    run('Install', False)
    assert hashes() == expected_original
finally:
    k.CloseHandle(handle)
results.append('Locked second target: earlier writes roll back')
assert not list(kit.rglob('*.tmp'))
report = {'passed': len(results), 'failed': 0, 'checks': results, 'manifestSha256': sha(ROOT / 'patch.json')}
(ROOT / 'reports/installer-test-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
