import argparse
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
parser = argparse.ArgumentParser()
parser.add_argument('--bundle', type=Path, default=ROOT,
                    help='Directory containing the installer and candidate patch.json')
parser.add_argument('--source', type=Path, default=ROOT / 'backups/original-build-25792521')
parser.add_argument('--previous-source', type=Path, default=ROOT / 'backups/original-20261009')
parser.add_argument('--report', type=Path, default=ROOT / 'reports/installer-test-results.json')
options = parser.parse_args()
manifest_path = options.bundle / 'patch.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
kit = ROOT / 'build' / 'installer-tests' / datetime.now().strftime('%Y%m%d-%H%M%S') / '中文路径 有空格' / 'assembly_kit'
assert not kit.exists(), 'Use a fresh isolated test directory'
kit.mkdir(parents=True)
for record in manifest['files']:
    target = kit / record['path']
    target.parent.mkdir(parents=True, exist_ok=True)
    source = options.source / target.name
    assert hashlib.sha256(source.read_bytes()).hexdigest().upper() == record['originalSha256']
    shutil.copyfile(source, target)
(kit / 'binaries/tweak.modder.x64.exe').write_bytes(b'Isolated installer test fixture')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()

def hashes():
    return {r['path']: sha(kit / r['path']) for r in manifest['files']}

results = []
def run(action, success=True):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                             str(options.bundle / 'Install-TerryCN.ps1'), '-Action', action,
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

def backup_path(record):
    return kit / 'Terry-CN-backup' / (Path(record['path']).name + '.' + record['originalSha256'][:16] + '.original')


def reconstruct(record, source):
    data = bytearray(source.read_bytes())
    assert sha(source) == record['originalSha256']
    if 'replacement' in record:
        data = base64.b64decode(record['replacement'])
    else:
        for edit in record['edits']:
            before, after = (base64.b64decode(edit[key]) for key in ['before', 'after'])
            assert len(before) == len(after)
            assert data[edit['offset']:edit['offset'] + len(before)] == before
            data[edit['offset']:edit['offset'] + len(after)] = after
        data.extend(base64.b64decode(record['append']))
    assert hashlib.sha256(data).hexdigest().upper() == record['patchedSha256']
    return data


# An older official DLL must never be accepted as the new build's backup,
# even when placed under the expected filename.
changed = [r for r in manifest['files']
           if sha(options.previous_source / Path(r['path']).name) != r['originalSha256']]
if changed:
    record = changed[0]
    current_backup = backup_path(record)
    verified_new_backup = current_backup.read_bytes()
    current_backup.write_bytes((options.previous_source / Path(record['path']).name).read_bytes())
    before = hashes()
    run('Install', False)
    assert hashes() == before
    current_backup.write_bytes(verified_new_backup)
    results.append('Old original under new backup name: rejects before any target write')

historical_inputs = {}
for version in ['R2', 'R3', 'R4', 'R5', 'v0.1.0']:
    if version == 'R2':
        fixture = ROOT / 'tests/fixtures/patch-r2.json'
        previous = json.loads(fixture.read_text(encoding='utf-8'))
        historical_inputs[version] = sha(fixture)
    else:
        filename = 'Terry-CN-WH3-v0.1.0.zip' if version == 'v0.1.0' else f'Terry-CN-WH3-20261010-{version}.zip'
        archive_path = ROOT / filename
        expected = Path(str(archive_path) + '.sha256').read_text(encoding='utf-8-sig').split()[0].upper()
        assert sha(archive_path) == expected
        historical_inputs[version] = expected
        with zipfile.ZipFile(archive_path) as archive:
            assert archive.testzip() is None
            previous = json.loads(archive.read('patch.json'))

    # Recreate the actual old installation, including targets which were not
    # patched until later releases, with independently verified old originals.
    for record in manifest['files']:
        shutil.copyfile(options.previous_source / Path(record['path']).name, kit / record['path'])
    for record in previous['files']:
        original = options.previous_source / Path(record['path']).name
        (kit / record['path']).write_bytes(reconstruct(record, original))
        old_backup = backup_path(record)
        if old_backup.exists():
            assert sha(old_backup) == record['originalSha256']
        else:
            shutil.copyfile(original, old_backup)
    preserved_backups = {p.name: sha(p) for p in (kit / 'Terry-CN-backup').glob('*.original')}

    if changed:
        before = hashes()
        run('Install', False)
        assert hashes() == before
        results.append(f'{version} on old upstream build: refuses without changing targets')
        # Steam updates the three changed CA DLLs and leaves unchanged depot
        # files alone: old translated Qt/tooltips coexist with new CA binaries.
        for record in changed:
            shutil.copyfile(options.source / Path(record['path']).name, kit / record['path'])

    if version in ['R2', 'v0.1.0']:
        missing = backup if version == 'R2' else backup_path(next(r for r in manifest['files'] if Path(r['path']).name == 'Qt5Widgets.dll'))
        moved_backup = missing.with_name(missing.name + '.test-held')
        assert not moved_backup.exists()
        missing.rename(moved_backup)
        try:
            before = hashes()
            run('Install', False)
            assert hashes() == before
        finally:
            moved_backup.rename(missing)
        results.append(f'{version} upgrade without required unchanged-file backup: all targets unchanged')
    run('Install')
    assert hashes() == expected_patched
    mode = 'after official Steam update' if changed else 'direct upgrade'
    results.append(f'{version} {mode}: all target hashes match')
    run('Restore')
    assert hashes() == expected_original
    assert all(sha(kit / 'Terry-CN-backup' / name) == value for name, value in preserved_backups.items())
    results.append(f'{version} restore: exact current originals; all earlier backups preserved')

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
report = {'passed': len(results), 'failed': 0, 'checks': results,
          'manifestSha256': sha(manifest_path), 'installerSha256': sha(options.bundle / 'Install-TerryCN.ps1'),
          'historicalInputSha256': historical_inputs, 'isolatedDirectory': str(kit.relative_to(ROOT))}
options.report.parent.mkdir(parents=True, exist_ok=True)
options.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
