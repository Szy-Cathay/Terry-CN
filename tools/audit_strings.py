"""Inventory literal QStrings and display imports without modifying installed files."""
import json
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


if __name__ == '__main__':
    source = Path(sys.argv[1])
    dest = Path(sys.argv[2])
    names = ['tweak_terrainmetadataeditor.modder.x64.dll', 'qttoolutility.modder.x64.dll']
    result = {name: inventory(source / name) for name in names}
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print({k: len(v) for k, v in result.items()})
