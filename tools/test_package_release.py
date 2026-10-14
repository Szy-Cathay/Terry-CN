"""Reject unverified release evidence in an isolated packaging directory."""
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
stage = ROOT / 'build/package-tests' / datetime.now().strftime('%Y%m%d-%H%M%S')
stage.mkdir(parents=True, exist_ok=False)
(stage / 'tools').mkdir()
(stage / 'reports').mkdir()
manifest = json.loads((ROOT / 'patch.json').read_text(encoding='utf-8'))
version = manifest['version']
names = ['patch.json', 'source-hashes.json', 'Install-TerryCN.ps1', '安装汉化.cmd',
         '恢复英文.cmd', '检查安装.cmd', '使用说明.txt', '验证说明.txt', f'发布说明-{version}.txt']
names += [p.name for p in ROOT.glob('translations*.zh-CN.json')]
for name in names:
    shutil.copyfile(ROOT / name, stage / name)
shutil.copyfile(ROOT / 'tools/package_release.py', stage / 'tools/package_release.py')
for path in (ROOT / 'reports').glob('*.json'):
    shutil.copyfile(path, stage / 'reports' / path.name)

cases = [
    ('scene-roundtrip.json', 'englishRoundtripVerified', False, 'confirmed scene roundtrip'),
    ('scene-roundtrip.json', 'payloadSha256', '0' * 64, 'another payload'),
    ('font-ui-verification.json', 'passed', False, 'actual menu and toolbar checks'),
    ('static-template-tests.json', 'manifestSha256', '0' * 64, 'Stale report'),
    ('installer-test-results.json', 'installerSha256', '0' * 64, 'Installer changed after testing'),
]
checks = []
for name, field, value, expected in cases:
    path = stage / 'reports' / name
    original = path.read_bytes()
    invalid = json.loads(original)
    invalid[field] = value
    path.write_text(json.dumps(invalid, ensure_ascii=False), encoding='utf-8')
    try:
        result = subprocess.run([sys.executable, str(stage / 'tools/package_release.py')],
                                capture_output=True, text=True, encoding='utf-8', errors='replace')
        assert result.returncode != 0 and expected in result.stderr, (name, field, result.stdout, result.stderr)
        assert not list(stage.glob('*.zip')), 'Invalid evidence produced an archive'
        checks.append(f'{name}: invalid {field} rejected before ZIP creation')
    finally:
        path.write_bytes(original)
report = {'passed': len(checks), 'failed': 0, 'checks': checks,
          'manifestSha256': hashlib.sha256((ROOT / 'patch.json').read_bytes()).hexdigest().upper(),
          'packagerSha256': hashlib.sha256((ROOT / 'tools/package_release.py').read_bytes()).hexdigest().upper()}
(ROOT / 'reports/package-gate-tests.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
