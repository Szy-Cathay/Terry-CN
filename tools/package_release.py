"""Package only the distributable translation differences and installation tools."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    'Install-TerryCN.ps1', 'patch.json', '安装汉化.cmd', '恢复英文.cmd',
    '检查安装.cmd', '使用说明.txt', '验证说明.txt',
]
output = ROOT / 'Terry-CN-WH3-20261010-R6.zip'
assert not output.exists(), 'Recycle an earlier delivery before rebuilding the archive'
manifest = json.loads((ROOT / 'patch.json').read_text(encoding='utf-8'))
assert len(manifest['files']) == 5 and manifest['version'] == '2026-10-10 R6'
manifest_hash = hashlib.sha256((ROOT / 'patch.json').read_bytes()).hexdigest().upper()
hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest().upper() for name in FILES}
for report in ['native-hook-tests.json', 'installer-test-results.json', 'patch-integrity-tests.json', 'static-template-tests.json', 'font-tests.json']:
    result = json.loads((ROOT / 'reports' / report).read_text(encoding='utf-8'))
    assert result['failed'] == 0 and result['passed'] > 0, report
    if report == 'native-hook-tests.json':
        assert result['qtCopyOwnershipChecks'] == 600, 'Project-title QString lifetime was not tested'
        for name, digest in result['catalogSha256'].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest().upper() == digest, 'Stale native report: ' + name
    else:
        assert result['manifestSha256'] == manifest_hash, 'Stale report: ' + report
scene = json.loads((ROOT / 'reports/scene-roundtrip.json').read_text(encoding='utf-8'))
assert scene['manifestSha256'] == manifest_hash and scene['englishRoundtripByteIdentical'], 'Current delivery needs a real scene roundtrip'
font_ui = json.loads((ROOT / 'reports/font-ui-verification.json').read_text(encoding='utf-8'))
assert font_ui['manifestSha256'] == manifest_hash and font_ui['passed'], 'Current delivery needs actual menu and toolbar checks'
checksum = ''.join(f'{digest}  {name}\n' for name, digest in hashes.items())
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name in FILES:
        archive.write(ROOT / name, name)
    archive.writestr('文件校验.sha256', checksum.encode('utf-8-sig'))
with zipfile.ZipFile(output) as archive:
    assert archive.testzip() is None, 'ZIP CRC mismatch'
    assert set(archive.namelist()) == set(FILES) | {'文件校验.sha256'}
    for name, digest in hashes.items():
        assert hashlib.sha256(archive.read(name)).hexdigest().upper() == digest
digest = hashlib.sha256(output.read_bytes()).hexdigest().upper()
output.with_suffix('.zip.sha256').write_text(f'{digest}  {output.name}\n', encoding='utf-8')
report = {'file': output.name, 'size': output.stat().st_size, 'sha256': digest,
          'crc': 'all passed', 'files': hashes, 'fullOfficialBinariesIncluded': False}
(ROOT / 'reports/package-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
