"""Exercise patched QStringLiteral data through the installed, original Qt ABI.

Uses every declared reference from the candidate DLL, then Qt's real arg/copy
and destructor operations. Dynamic Unicode values, paths, percent signs and
HTML punctuation survive unchanged; original static data remains immutable.
"""
import argparse
import ctypes as c
import hashlib
import json
import os
import re
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/python-libs'))
import pefile

parser = argparse.ArgumentParser()
parser.add_argument('build', type=Path)
parser.add_argument('--qt-core', type=Path, required=True)
options = parser.parse_args()
with os.add_dll_directory(str(options.qt_core.resolve().parent)):
    qt = c.WinDLL(str(options.qt_core.resolve()))
arg = getattr(qt, '?arg@QString@@QEBA?AV1@AEBV1@HVQChar@@@Z')
arg.argtypes = [c.c_void_p, c.c_void_p, c.c_void_p, c.c_int, c.c_uint16]
arg.restype = c.c_void_p
assign = getattr(qt, '??4QString@@QEAAAEAV0@AEBV0@@Z')
assign.argtypes = [c.c_void_p, c.c_void_p]
assign.restype = c.c_void_p
create = getattr(qt, '?fromAscii_helper@QString@@CAPEAU?$QTypedArrayData@G@@PEBDH@Z')
create.argtypes = [c.c_char_p, c.c_int]
create.restype = c.c_void_p
destroy = getattr(qt, '??1QString@@QEAA@XZ')
destroy.argtypes = [c.c_void_p]
destroy.restype = None
from_utf8 = getattr(qt, '?fromUtf8@QString@@SA?AV1@PEBDH@Z')
from_utf8.argtypes = [c.c_void_p, c.c_char_p, c.c_int]
from_utf8.restype = c.c_void_p
append = getattr(qt, '?append@QString@@QEAAAEAV1@AEBV1@@Z')
append.argtypes = [c.c_void_p, c.c_void_p]
append.restype = c.c_void_p
append_utf8 = getattr(qt, '?append@QString@@QEAAAEAV1@PEBD@Z')
append_utf8.argtypes = [c.c_void_p, c.c_char_p]
append_utf8.restype = c.c_void_p
assign_utf8 = getattr(qt, '??4QString@@QEAAAEAV0@PEBD@Z')
assign_utf8.argtypes = [c.c_void_p, c.c_char_p]
assign_utf8.restype = c.c_void_p
construct_utf8 = getattr(qt, '??0QString@@QEAA@PEBD@Z')
construct_utf8.argtypes = [c.c_void_p, c.c_char_p]
construct_utf8.restype = c.c_void_p


def read(obj):
    data = obj.value
    return c.string_at(data + c.c_int64.from_address(data + 16).value,
                       c.c_int.from_address(data + 4).value * 2).decode('utf-16-le')


def make(text):
    encoded = text.encode('utf-16-le')
    buf = c.create_string_buffer(struct.pack('<iII4xq', -1, len(encoded) // 2, 0, 24) + encoded + b'\0\0')
    return buf, c.c_void_p(c.addressof(buf))


coverage = json.loads((options.build / 'coverage.json').read_text(encoding='utf-8'))
checks, sites, substituted, fragments = 0, 0, 0, 0
for name, records in coverage.items():
    pe = pefile.PE(str(options.build / name), fast_load=True)
    for item in records:
        if item.get('auditedUtf8Fragment'):
            rva = int(item['rva'], 16)
            data_rva = rva + 7 + struct.unpack_from('<i', pe.get_data(rva, 7), 3)[0]
            encoded = item['translation'].encode('utf-8')
            assert pe.get_data(data_rva, len(encoded) + 1) == encoded + b'\0'
            length = -1
            if 'lengthByteRva' in item:
                length = pe.get_data(int(item['lengthByteRva'], 16), 1)[0] - item['lengthBias']
                assert length == len(encoded)
            result = c.c_void_p()
            consumer = item['consumer']
            if 'fromAscii_helper' in consumer:
                result = c.c_void_p(create(encoded, length))
            elif consumer.startswith('??0QString'):
                construct_utf8(c.byref(result), encoded)
            elif consumer.startswith('??4QString') or consumer.startswith('?append@QString'):
                result = c.c_void_p(create(b'', 0))
                operation = assign_utf8 if consumer.startswith('??4QString') else append_utf8
                assert operation(c.byref(result), encoded) == c.addressof(result)
            else:
                assert from_utf8(c.byref(result), encoded, length) == c.addressof(result)
            assert read(result) == item['translation'], (name, item['rva'], consumer)
            value = 'D:/用户的目录/asset_01.tiff & 50%'
            value_buf, value_obj = make(value)
            append(c.byref(result), c.byref(value_obj))
            assert read(result) == item['translation'] + value
            destroy(c.byref(result))
            assert read(value_obj) == value
            fragments += 1
            checks += 1
            continue
        if not item.get('staticQStringLiteral'):
            continue
        rva = int(item['rva'], 16)
        instruction = pe.get_data(rva, 7)
        data_rva = rva + 7 + struct.unpack_from('<i', instruction, 3)[0]
        assert data_rva == int(item['translatedDataRva'], 16)
        header = pe.get_data(data_rva, 24)
        ref, length, allocated, offset = struct.unpack('<iII4xq', header)
        assert (ref, allocated, offset) == (-1, 0, 24)
        raw = pe.get_data(data_rva, 24 + 2 * length + 2)
        source = c.create_string_buffer(raw)
        static_obj = c.c_void_p(c.addressof(source))
        expected = item['translation']
        assert read(static_obj) == expected
        assert sorted(re.findall(r'%L?\d+', item['source'])) == sorted(re.findall(r'%L?\d+', expected))
        # Copy into a normal Qt object exactly as a literal constructor would.
        current = c.c_void_p(create(b'', 0))
        assign(c.byref(current), c.byref(static_obj))
        for number in sorted({int(n) for n in re.findall(r'%L?(\d+)', expected)}):
            value = f'数值{number} D:/未翻译/asset_{number}.terry & <tag> 50%'
            value_buf, value_obj = make(value)
            result = c.c_void_p()
            assert arg(c.byref(current), c.byref(result), c.byref(value_obj), 0, 32) == c.addressof(result)
            destroy(c.byref(current))
            current = result
            expected = re.sub(r'%L?' + str(number) + r'(?!\d)', lambda _: value, expected)
            assert read(current) == expected, (name, item['rva'], number)
            assert read(value_obj) == value
            substituted += 1
            checks += 1
        assert read(current) == expected
        destroy(c.byref(current))
        assert source.raw[:len(raw)] == raw and read(static_obj) == item['translation']
        sites += 1
        checks += 1

result = {'passed': checks, 'failed': 0, 'staticLiteralSites': sites,
          'utf8FragmentSites': fragments,
          'qtArgumentSubstitutions': substituted,
          'manifestSha256': hashlib.sha256((options.build / 'patch.json').read_bytes()).hexdigest().upper(),
          'checks': ['Candidate LEA operands resolve to declared Qt data', 'Real QString::arg and copy/destruction',
                     'Real UTF-8 construction, assignment and concatenation',
                     'Unicode/path/percent/HTML parameters preserved', 'Placeholder order and multiplicity',
                     'Immutable literal refcounts and data preserved']}
(ROOT / 'reports/static-template-tests.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
