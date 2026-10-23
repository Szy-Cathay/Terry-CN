import argparse
import base64
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/python-libs'))
import pefile
pefile.MAX_IMPORT_SYMBOLS = 65536

parser = argparse.ArgumentParser()
parser.add_argument('build', type=Path)
parser.add_argument('--source', type=Path, default=ROOT / 'backups/original-build-25922678')
parser.add_argument('--report', type=Path, default=ROOT / 'reports/patch-integrity-tests.json')
options = parser.parse_args()
build = options.build
manifest = json.loads((build / 'patch.json').read_text(encoding='utf-8'))
coverage = json.loads((build / 'coverage.json').read_text(encoding='utf-8'))
protected = set(json.loads((ROOT / 'protected-identifiers.json').read_text(encoding='utf-8'))['identifiers'])
permitted_label_sites = {0x1cc73, 0x19885, 0x1ba34, 0x1c762, 0x1cfd6}
checks = []
for r in manifest['files']:
    original = (options.source / Path(r['path']).name).read_bytes()
    result = bytearray(original)
    if 'replacement' in r:
        result = base64.b64decode(r['replacement'])
        a, b = ET.fromstring(original), ET.fromstring(result)
        assert [(e.tag, e.attrib) for e in a.iter()] == [(e.tag, e.attrib) for e in b.iter()]
        checks.append('Status tooltip schema and tool IDs unchanged')
    else:
        occupied = set()
        for edit in r['edits']:
            offset = edit['offset']
            before, after = (base64.b64decode(edit[k]) for k in ['before', 'after'])
            assert before == original[offset:offset + len(before)] and len(before) == len(after)
            assert not occupied.intersection(range(offset, offset + len(before)))
            occupied.update(range(offset, offset + len(before)))
            result[offset:offset + len(after)] = after
        result.extend(base64.b64decode(r['append']))
        pe, patched = pefile.PE(data=original), pefile.PE(data=bytes(result))
        assert patched.OPTIONAL_HEADER.DllCharacteristics == pe.OPTIONAL_HEADER.DllCharacteristics
        assert patched.OPTIONAL_HEADER.AddressOfEntryPoint == pe.OPTIONAL_HEADER.AddressOfEntryPoint
        assert len(patched.sections) == len(pe.sections) + 1
        allowed_code_changes = set()
        for item in coverage[Path(r['path']).name]:
            rva = int(item['rva'], 16)
            if item.get('fontUi'):
                before, after = bytes.fromhex(item['beforeHex']), bytes.fromhex(item['afterHex'])
                assert pe.get_data(rva, len(before)) == before
                assert patched.get_data(rva, len(after)) == after
                allowed_code_changes.update(range(pe.get_offset_from_rva(rva), pe.get_offset_from_rva(rva) + len(before)))
            elif 'displayHook' in item:
                allowed_code_changes.update(range(pe.get_offset_from_rva(rva), pe.get_offset_from_rva(rva) + 6))
            elif item.get('auditedUtf8Fragment'):
                assert item['source'] not in protected, item
                allowed_code_changes.update(range(pe.get_offset_from_rva(rva) + 3, pe.get_offset_from_rva(rva) + 7))
                if 'lengthByteRva' in item:
                    allowed_code_changes.add(pe.get_offset_from_rva(int(item['lengthByteRva'], 16)))
                encoded = item['translation'].encode('utf-8')
                assert patched.get_data(int(item['translatedDataRva'], 16), len(encoded) + 1) == encoded + b'\0'
            elif item.get('staticQStringLiteral'):
                assert item['source'] not in protected, item
                allowed_code_changes.update(range(pe.get_offset_from_rva(rva) + 3, pe.get_offset_from_rva(rva) + 7))
                data_rva = int(item['translatedDataRva'], 16)
                encoded = item['translation'].encode('utf-16-le')
                assert patched.get_data(data_rva + 24, len(encoded) + 2) == encoded + b'\0\0'
            elif item.get('auditedDisplayLabel'):
                if item.get('lengthRva'):
                    allowed_code_changes.add(pe.get_offset_from_rva(int(item['lengthRva'], 16)))
                allowed_code_changes.update(range(pe.get_offset_from_rva(rva) + 3, pe.get_offset_from_rva(rva) + 7))
            else:
                assert item['source'] not in protected or rva in permitted_label_sites, item
                offset = pe.get_offset_from_rva(rva)
                allowed_code_changes.update(range(offset + 1, offset + 5))
                allowed_code_changes.update(range(offset + 8, offset + 12))
        for section in pe.sections:
            a, b = section.PointerToRawData, section.PointerToRawData + section.SizeOfRawData
            changed = {i for i in range(a, b) if original[i] != result[i]}
            if section.Characteristics & 0x20000000:
                assert changed <= allowed_code_changes, (r['path'], sorted(changed - allowed_code_changes)[:10])
            else:
                assert not changed, (r['path'], section.Name)
        assert patched.verify_checksum()
        original_relocs = {(e.type, e.rva) for block in pe.DIRECTORY_ENTRY_BASERELOC for e in block.entries if e.type}
        new_relocs = {(e.type, e.rva) for block in patched.DIRECTORY_ENTRY_BASERELOC for e in block.entries if e.type}
        assert original_relocs <= new_relocs
        original_runtime = {(e.struct.BeginAddress, e.struct.EndAddress, e.struct.UnwindData) for e in pe.DIRECTORY_ENTRY_EXCEPTION}
        patched_runtime = {(e.struct.BeginAddress, e.struct.EndAddress, e.struct.UnwindData) for e in patched.DIRECTORY_ENTRY_EXCEPTION}
        assert original_runtime <= patched_runtime
        checks.append(Path(r['path']).name + ': only declared display sites changed; original data/imports/relocations preserved')
    assert hashlib.sha256(original).hexdigest().upper() == r['originalSha256']
    assert hashlib.sha256(result).hexdigest().upper() == r['patchedSha256']
    assert bytes(result) == (build / Path(r['path']).name).read_bytes()
    checks.append(r['path'] + ': differential reconstruction SHA-256 verified')
result = {'passed': len(checks), 'failed': 0, 'checks': checks,
          'manifestSha256': hashlib.sha256((build / 'patch.json').read_bytes()).hexdigest().upper()}
options.report.parent.mkdir(parents=True, exist_ok=True)
options.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
