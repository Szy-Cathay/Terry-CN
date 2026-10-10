"""Inventory literal QStrings and display imports without modifying installed files."""
import json
import argparse
import hashlib
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/python-libs'))
import pefile
pefile.MAX_IMPORT_SYMBOLS = 65536


def imports(pe):
    return {i.address - pe.OPTIONAL_HEADER.ImageBase: i.name.decode()
            for lib in pe.DIRECTORY_ENTRY_IMPORT for i in lib.imports if i.name}


def inventory(path):
    data = path.read_bytes()
    pe = pefile.PE(data=data)
    names = imports(pe)
    result = []
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        for m in re.finditer(rb'\xba(.{4})\x48\x8d\x0d(.{4})\xff\x15(.{4})', section.get_data(), re.S):
            rva = section.VirtualAddress + m.start()
            function = rva + 18 + struct.unpack('<i', m[3])[0]
            if 'fromAscii_helper@QString' not in names.get(function, ''):
                continue
            size = struct.unpack('<I', m[1])[0]
            if size > 4096:
                continue
            text_rva = rva + 12 + struct.unpack('<i', m[2])[0]
            try:
                text = pe.get_data(text_rva, size).decode('utf-8')
            except (UnicodeDecodeError, pefile.PEFormatError):
                continue
            result.append({'rva': hex(rva), 'source': text})
    return result


def data_strings(path):
    """Collect ordinary narrow/wide UI candidates, including non-Qt producers.

    This deliberately includes internal identifiers and logs. An unmapped count
    is an audit queue, never a translation percentage or permission to patch.
    """
    pe = pefile.PE(str(path), fast_load=True)
    result = []
    for section in pe.sections:
        if section.Characteristics & 0x20000000:
            continue
        raw = section.get_data()
        for pattern, encoding in [(rb'[\x20-\x7e\r\n\t]{4,}\x00', 'ascii'),
                                  (rb'(?:[\x20-\x7e]\x00){4,}\x00\x00', 'utf-16-le')]:
            for match in re.finditer(pattern, raw):
                text = match.group().decode(encoding).rstrip('\0')
                if re.search('[A-Za-z]{3}', text):
                    result.append({'rva': hex(section.VirtualAddress + match.start()),
                                   'encoding': encoding, 'source': text})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('dest', type=Path)
    parser.add_argument('--data-strings', action='store_true', help='Also scan ordinary ASCII/UTF-16 constants')
    parser.add_argument('--module', action='append', help='Module filename; repeat for shared producers such as Warscape')
    options = parser.parse_args()
    names = options.module or ['tweak_terrainmetadataeditor.modder.x64.dll', 'qttoolutility.modder.x64.dll']
    result = {}
    for name in names:
        path = options.source / name
        result[name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest().upper(),
                        'qstringLiterals': inventory(path)}
        if options.data_strings:
            result[name]['dataStrings'] = data_strings(path)
    dest = options.dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print({k: {field: len(v[field]) for field in ['qstringLiterals', 'dataStrings'] if field in v}
           for k, v in result.items()})
