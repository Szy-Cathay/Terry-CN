"""Package only the distributable translation differences and installation tools."""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    'Install-TerryCN.ps1', 'patch.json', '安装汉化.cmd', '恢复英文.cmd',
    '检查安装.cmd', '使用说明.txt', '验证说明.txt', '发布说明-v0.1.0.txt',
]
output = ROOT / 'Terry-CN-WH3-v0.1.0.zip'
assert not output.exists(), 'Recycle an earlier delivery before rebuilding the archive'
manifest = json.loads((ROOT / 'patch.json').read_text(encoding='utf-8'))
assert len(manifest['files']) == 5 and manifest['version'] == 'v0.1.0'
manifest_bytes = (ROOT / 'patch.json').read_bytes()
manifest_hash = hashlib.sha256(manifest_bytes).hexdigest().upper()
hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest().upper() for name in FILES}
# The first formal release renames the verified R6 build without changing its
# patch payload or installer. Reversing only the version field must reproduce
# the exact verified manifest before its historical evidence can be reused.
r6_manifest_hash = '2EFAB9F47C2CC07D9C85FB138DA66F40C853854B147B36FE57D1FAF2135ACC02'
r6_installer_hashes = {
    'Install-TerryCN.ps1': '0B578ACD3F3AD8EB790236AE6DB90AD99161A2D433278D966302313506F0DCBC',
    '安装汉化.cmd': '6CD4113282E93EA8028AB75561AB0774D9BE31AFAE9448653B045C3971D8E077',
    '恢复英文.cmd': '6D756DC8E6E307FC3F86ED0D4F6D9D1292C5D44CEEB01C5F6F4C8ECAA20E013B',
    '检查安装.cmd': 'CD8F3579EC3722216E2C7466125E20D8B2A1A3A72F9B0110FA7C15FBB1A9633E',
}
metadata_only = (
    hashlib.sha256(manifest_bytes.replace(b'"version": "v0.1.0"', b'"version": "2026-10-10 R6"', 1)).hexdigest().upper() == r6_manifest_hash
    and all(hashes[name] == digest for name, digest in r6_installer_hashes.items())
)
evidence_hashes = {manifest_hash} | ({r6_manifest_hash} if metadata_only else set())
inherited_reports = []

def check_evidence(name, result):
    assert result['manifestSha256'] in evidence_hashes, 'Stale report: ' + name
    if result['manifestSha256'] != manifest_hash:
        inherited_reports.append(name)

for report in ['native-hook-tests.json', 'installer-test-results.json', 'patch-integrity-tests.json', 'static-template-tests.json', 'font-tests.json']:
    result = json.loads((ROOT / 'reports' / report).read_text(encoding='utf-8'))
    assert result['failed'] == 0 and result['passed'] > 0, report
    if report == 'native-hook-tests.json':
        assert result['qtCopyOwnershipChecks'] == 600, 'Project-title QString lifetime was not tested'
        for name, digest in result['catalogSha256'].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest().upper() == digest, 'Stale native report: ' + name
    else:
        check_evidence(report, result)
scene = json.loads((ROOT / 'reports/scene-roundtrip.json').read_text(encoding='utf-8'))
check_evidence('scene-roundtrip.json', scene)
assert scene['englishRoundtripByteIdentical'], 'Current delivery needs a real scene roundtrip'
font_ui = json.loads((ROOT / 'reports/font-ui-verification.json').read_text(encoding='utf-8'))
check_evidence('font-ui-verification.json', font_ui)
assert font_ui['passed'], 'Current delivery needs actual menu and toolbar checks'
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
          'crc': 'all passed', 'files': hashes, 'fullOfficialBinariesIncluded': False,
          'version': manifest['version'], 'manifestSha256': manifest_hash,
          'versionMetadataOnly': metadata_only,
          'inheritedEvidence': {'manifestSha256': r6_manifest_hash, 'reports': inherited_reports} if inherited_reports else None}
(ROOT / 'reports/package-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
