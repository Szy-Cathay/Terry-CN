"""Execute every display mapping using the real Windows x64 ABI and ASLR.

Checks the native code, not a reimplementation of its comparisons. The fallback
captures all five argument slots, including the first stack argument.
"""
import argparse
import ctypes as c
import hashlib
import json
import os
import struct
from pathlib import Path
from display_hooks import DisplayPool

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--qt-core', type=Path, help='Original Qt5Core.dll for real QString ownership checks')
parser.add_argument('--report', type=Path, default=ROOT / 'reports/native-hook-tests.json')
options = parser.parse_args()
translations = {}
catalog_hashes = {}
for name in ['translations.zh-CN.json', 'translations.ui.zh-CN.json', 'translations.messages.zh-CN.json', 'translations.display.zh-CN.json', 'translations.properties.zh-CN.json', 'translations.extended.zh-CN.json', 'translations.engine.zh-CN.json', 'translations.templates.zh-CN.json']:
    translations.update(json.loads((ROOT / name).read_text(encoding='utf-8-sig')))
    catalog_hashes[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest().upper()
# Paint/layout sinks also receive uppercase labels from Qt styles.
translations.update({s.upper(): t for s, t in list(translations.items()) if len(s) <= 60 and '%' not in s})
k = c.WinDLL('kernel32', use_last_error=True)
k.VirtualAlloc.argtypes = [c.c_void_p, c.c_size_t, c.c_uint32, c.c_uint32]
k.VirtualAlloc.restype = c.c_void_p
k.VirtualFree.argtypes = [c.c_void_p, c.c_size_t, c.c_uint32]
signature = c.WINFUNCTYPE(c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p, c.c_void_p)
captured = []


@signature
def fallback(a, b, d, e, f):
    captured.append((a, b, d, e, f))
    return 123


def qstring(text):
    encoded = text.encode('utf-16-le')
    data = c.create_string_buffer(struct.pack('<iII4xq', -1, len(encoded) // 2, 0, 24) + encoded + b'\0\0')
    obj = c.c_void_p(c.addressof(data))
    return data, obj


def read_qstring(obj):
    data = c.c_void_p.from_address(obj).value
    size = c.c_int.from_address(data + 4).value
    offset = c.c_int64.from_address(data + 16).value
    return c.string_at(data + offset, size * 2).decode('utf-16-le')


checks = 0
for kind, argument in [('qstring-argument', 'rdx'), ('qstring-argument', 'r8'), ('qstring-argument', 'r9'),
                       ('latin1-return', 'rdx'), ('translate-return', 'r8'), ('meta-translate-return', 'r8')]:
    pool = bytearray()
    dp = DisplayPool(pool, 0x1000, 0)
    start = dp.make_hook(translations, 0x100, kind, argument)
    memory = k.VirtualAlloc(None, 0x1000 + len(pool), 0x3000, 0x40)
    assert memory, c.get_last_error()
    try:
        c.memmove(memory + 0x1000, bytes(pool), len(pool))
        c.c_void_p.from_address(memory + 0x100).value = c.cast(fallback, c.c_void_p).value
        for rva in dp.relocations:
            pointer = c.c_uint64.from_address(memory + rva)
            pointer.value += memory
        native = signature(memory + start)
        for source in list(translations) + ['', 'unknown_custom_property_123', '用户自定义名称😀', 'N', 'Autopla', 'Autoplay-extra']:
            args = [0x1111, 0x2222, 0x3333, 0x4444, 0x5555]
            data, obj = qstring(source)
            original_data, original_obj = data.raw, obj.value
            if kind == 'qstring-argument':
                index = {'rdx': 1, 'r8': 2, 'r9': 3}[argument]
                args[index] = c.addressof(obj)
            else:
                result_obj = c.c_void_p()
                source_data = c.create_string_buffer(source.encode('utf-8'))
                result_index = 1 if kind == 'meta-translate-return' else 0
                args[result_index] = c.addressof(result_obj)
                args[1 if kind == 'latin1-return' else 2] = c.addressof(source_data)
                if kind == 'latin1-return':
                    args[2] = 0xffffffff
            captured.clear()
            value = native(*args)
            matched = source in translations and source != translations[source] and (source.isascii() or kind == 'qstring-argument')
            if kind == 'qstring-argument':
                assert value == 123 and len(captured) == 1
                expected = list(args)
                expected[index] = captured[0][index]
                assert tuple(expected) == captured[0], (kind, argument, source, captured)
                assert read_qstring(captured[0][index]) == translations.get(source, source), source
                if not matched:
                    assert captured[0][index] == args[index]
            elif matched:
                assert not captured and value == args[result_index]
                assert read_qstring(args[result_index]) == translations[source]
            else:
                assert value == 123 and captured == [tuple(args)]
            assert data.raw == original_data and obj.value == original_obj, 'Input mutated'
            checks += 1
        if kind == 'latin1-return':
            # Explicit-length slices and null pointers must never be overread.
            out = c.c_void_p()
            text = c.create_string_buffer(b'Autoplay')
            for length in [0, 1, 7, 8, 9]:
                args = (c.addressof(out), c.addressof(text), length, 0x4444, 0x5555)
                captured.clear()
                assert native(*args) == 123 and captured == [tuple(x or None for x in args)]
                checks += 1
        args = [0x1111, 0x2222, 0x3333, 0x4444, 0x5555]
        args[{'rdx': 1, 'r8': 2, 'r9': 3}[argument]] = None
        captured.clear()
        assert native(*args) == 123 and captured == [tuple(args)]
        checks += 1
    finally:
        k.VirtualFree(memory, 0, 0x8000)
ownership_checks = 0
if options.qt_core:
    # The project-title composer uses a const copy assignment instead of moving
    # from an immutable translated QString. Exercise the actual bundled Qt ABI
    # with both static translated data and heap-owned passthrough strings.
    with os.add_dll_directory(str(options.qt_core.resolve().parent)):
        qt = c.WinDLL(str(options.qt_core.resolve()))
    assign = getattr(qt, '??4QString@@QEAAAEAV0@AEBV0@@Z')
    assign.argtypes = [c.c_void_p, c.c_void_p]
    assign.restype = c.c_void_p
    create = getattr(qt, '?fromAscii_helper@QString@@CAPEAU?$QTypedArrayData@G@@PEBDH@Z')
    create.argtypes = [c.c_char_p, c.c_int]
    create.restype = c.c_void_p
    destroy = getattr(qt, '??1QString@@QEAA@XZ')
    destroy.argtypes = [c.c_void_p]
    destroy.restype = None
    pool = bytearray()
    dp = DisplayPool(pool, 0x1000, 0)
    start = dp.make_hook(translations, 0x100, 'qstring-argument', 'rdx')
    memory = k.VirtualAlloc(None, 0x1000 + len(pool), 0x3000, 0x40)
    assert memory, c.get_last_error()
    try:
        c.memmove(memory + 0x1000, bytes(pool), len(pool))
        c.c_void_p.from_address(memory + 0x100).value = c.cast(assign, c.c_void_p).value
        for rva in dp.relocations:
            pointer = c.c_uint64.from_address(memory + rva)
            pointer.value += memory
        native = c.WINFUNCTYPE(c.c_void_p, c.c_void_p, c.c_void_p)(memory + start)
        for source in ['Prefab', 'Tile', 'Tile Map', 'battle', 'campaign', 'unmapped_custom_project_type']:
            for _ in range(100):
                obj = c.c_void_p(create(source.encode(), -1))
                dest = c.c_void_p(create(b'previous title', -1))
                original_pointer = obj.value
                original_ref = c.c_int.from_address(obj.value).value
                assert native(c.addressof(dest), c.addressof(obj)) == c.addressof(dest)
                assert obj.value == original_pointer and read_qstring(c.addressof(obj)) == source
                expected_ref = original_ref if source in translations else original_ref + 1
                assert c.c_int.from_address(obj.value).value == expected_ref
                assert read_qstring(c.addressof(dest)) == translations.get(source, source)
                destroy(c.addressof(obj))
                assert read_qstring(c.addressof(dest)) == translations.get(source, source)
                destroy(c.addressof(dest))
                ownership_checks += 1
    finally:
        k.VirtualFree(memory, 0, 0x8000)
    checks += ownership_checks
result = {'passed': checks, 'failed': 0, 'dictionaryEntriesIncludingStyleVariants': len(translations),
          'catalogSha256': catalog_hashes, 'qtCopyOwnershipChecks': ownership_checks,
          'longTextEntries': sum(len(s) > 160 for s in translations),
          'checks': ['All native mappings', 'ASLR relocated QString pointers', 'Five ABI arguments preserved',
                     'Original strings unchanged', 'Unknown/empty/Unicode passthrough', 'Explicit lengths and null passthrough']}
options.report.parent.mkdir(parents=True, exist_ok=True)
options.report.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
