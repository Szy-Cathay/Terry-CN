"""Run the candidate typography shim under ASLR and against Terry's real Qt."""
import argparse
import ctypes as c
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/python-libs'))
import pefile
pefile.MAX_IMPORT_SYMBOLS = 65536

parser = argparse.ArgumentParser()
parser.add_argument('build', type=Path)
parser.add_argument('--qt-bin', type=Path, required=True)
args = parser.parse_args()
pe = pefile.PE(str(args.build / 'tweak_terrainmetadataeditor.modder.x64.dll'))
metadata = next(x for x in json.loads((args.build / 'display-hooks.json').read_text())[
    'tweak_terrainmetadataeditor.modder.x64.dll'] if x['kind'] == 'terry-font-ui')
hook = metadata['menuHook']
begin, end, unwind = (int(hook[x], 16) for x in ['beginRva', 'endRva', 'unwindRva'])
k = c.WinDLL('kernel32', use_last_error=True)
k.VirtualAlloc.argtypes = [c.c_void_p, c.c_size_t, c.c_uint32, c.c_uint32]
k.VirtualAlloc.restype = c.c_void_p
k.VirtualFree.argtypes = [c.c_void_p, c.c_size_t, c.c_uint32]
k.RtlAddFunctionTable.argtypes = [c.c_void_p, c.c_uint32, c.c_uint64]
k.RtlAddFunctionTable.restype = c.c_bool
k.RtlDeleteFunctionTable.argtypes = [c.c_void_p]
k.RtlLookupFunctionEntry.argtypes = [c.c_uint64, c.POINTER(c.c_uint64), c.c_void_p]
k.RtlLookupFunctionEntry.restype = c.c_void_p
memory = k.VirtualAlloc(None, pe.OPTIONAL_HEADER.SizeOfImage, 0x3000, 0x40)
assert memory and memory != pe.OPTIONAL_HEADER.ImageBase
mapped = pe.get_memory_mapped_image()
c.memmove(memory, mapped, len(mapped))
for block in pe.DIRECTORY_ENTRY_BASERELOC:
    for entry in block.entries:
        if entry.type == 10:
            value = c.c_uint64.from_address(memory + entry.rva)
            value.value += memory - pe.OPTIONAL_HEADER.ImageBase
table = c.create_string_buffer(struct.pack('<III', begin, end, unwind))
assert k.RtlAddFunctionTable(table, 1, memory)
checks, widths = [], {}


def read_qstring(pointer):
    data = c.c_void_p.from_address(pointer).value
    size = c.c_int.from_address(data + 4).value
    offset = c.c_int64.from_address(data + 16).value
    return c.string_at(data + offset, size * 2).decode('utf-16-le')


def qstring(text):
    value = text.encode('utf-16-le')
    data = c.create_string_buffer(struct.pack('<iII4xq', -1, len(value) // 2, 0, 24) + value + b'\0\0')
    return data, c.c_void_p(c.addressof(data))


def bind(dll, name, result, *parameters):
    method = getattr(dll, name)
    method.restype, method.argtypes = result, list(parameters)
    return method


def set_iat(rva, method):
    c.c_void_p.from_address(memory + rva).value = c.cast(method, c.c_void_p).value


calls = []
@c.WINFUNCTYPE(None, c.c_void_p, c.c_void_p)
def stylesheet(widget, text):
    calls.append(('style', widget, read_qstring(text)))


@c.WINFUNCTYPE(c.c_void_p, c.c_void_p)
def menubar(widget):
    calls.append(('menu', widget))
    return 0x76543210


try:
    set_iat(0x64e1c0, stylesheet)
    set_iat(0x64e708, menubar)
    native = c.WINFUNCTYPE(c.c_void_p, c.c_void_p)(memory + begin)
    for i in range(600):
        calls.clear()
        widget = 0x12345670 + i * 16
        assert native(widget) == 0x76543210
        assert calls == [('style', widget, metadata['stylesheet']), ('menu', widget)]
    checks.append('600 relocated native calls preserve this, call order and original menuBar result')
    imagebase = c.c_uint64()
    assert k.RtlLookupFunctionEntry(memory + begin + 12, c.byref(imagebase), None)
    assert imagebase.value == memory
    assert c.string_at(memory + unwind, 8) == bytes.fromhex('01 04 01 00 04 42 00 00')
    checks.append('Windows runtime resolves the non-leaf hook unwind record')

    search = os.add_dll_directory(str(args.qt_bin.resolve()))
    os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = str(args.qt_bin.resolve() / 'platforms')
    core = c.WinDLL(str(args.qt_bin / 'Qt5Core.dll'))
    gui = c.WinDLL(str(args.qt_bin / 'Qt5Gui.dll'))
    widgets = c.WinDLL(str(args.qt_bin / 'Qt5Widgets.dll'))
    ptr = c.c_void_p
    create_app = bind(widgets, '??0QApplication@@QEAA@AEAHPEAPEADH@Z', ptr, ptr, ptr, ptr, c.c_int)
    destroy_app = bind(widgets, '??1QApplication@@UEAA@XZ', None, ptr)
    create_window = bind(widgets, '??0QMainWindow@@QEAA@PEAVQWidget@@V?$QFlags@W4WindowType@Qt@@@@@Z', ptr, ptr, ptr, c.c_int)
    destroy_window = bind(widgets, '??1QMainWindow@@UEAA@XZ', None, ptr)
    create_font = bind(gui, '??0QFont@@QEAA@AEBVQString@@HH_N@Z', ptr, ptr, ptr, c.c_int, c.c_int, c.c_bool)
    destroy_font = bind(gui, '??1QFont@@QEAA@XZ', None, ptr)
    font_family = bind(gui, '?family@QFont@@QEBA?AVQString@@XZ', ptr, ptr, ptr)
    font_points = bind(gui, '?pointSize@QFont@@QEBAHXZ', c.c_int, ptr)
    widget_font = bind(widgets, '?font@QWidget@@QEBAAEBVQFont@@XZ', ptr, ptr)
    polish = bind(widgets, '?ensurePolished@QWidget@@QEBAXXZ', None, ptr)
    destroy_string = bind(core, '??1QString@@QEAA@XZ', None, ptr)
    create_image = bind(gui, '??0QImage@@QEAA@AEBVQSize@@W4Format@0@@Z', ptr, ptr, ptr, c.c_int)
    destroy_image = bind(gui, '??1QImage@@UEAA@XZ', None, ptr)
    create_metrics = bind(gui, '??0QFontMetrics@@QEAA@AEBVQFont@@PEAVQPaintDevice@@@Z', ptr, ptr, ptr, ptr)
    destroy_metrics = bind(gui, '??1QFontMetrics@@QEAA@XZ', None, ptr)
    advance = bind(gui, '?horizontalAdvance@QFontMetrics@@QEBAHAEBVQString@@H@Z', c.c_int, ptr, ptr, c.c_int)
    height = bind(gui, '?height@QFontMetrics@@QEBAHXZ', c.c_int, ptr)
    app, window = c.create_string_buffer(4096), c.create_string_buffer(4096)
    argc = c.c_int(1)
    argv = (c.c_char_p * 2)(b'TerryFontRegression', None)
    create_app(app, c.byref(argc), argv, 0x050c00)
    try:
        create_window(window, None, 0)
        try:
            set_iat(0x64e1c0, getattr(widgets, '?setStyleSheet@QWidget@@QEAAXAEBVQString@@@Z'))
            set_iat(0x64e708, getattr(widgets, '?menuBar@QMainWindow@@QEBAPEAVQMenuBar@@XZ'))
            menu = native(window)
            assert menu
            polish(window)
            polish(menu)
            family_result = c.c_void_p()
            font_family(widget_font(menu), c.byref(family_result))
            assert read_qstring(c.addressof(family_result)) == metadata['family'], read_qstring(c.addressof(family_result))
            destroy_string(c.byref(family_result))
            assert font_points(widget_font(menu)) == 10
            checks.append('Actual Qt main window and menu bar use Microsoft YaHei UI at 10 pt')

            lea = pe.get_data(0x28034a, 7)
            family_pointer = memory + 0x280351 + struct.unpack('<i', lea[3:])[0]
            points = pe.get_data(0x280346, 4)[3] - 1
            assert points == metadata['iconPointSize']
            font, metrics = c.create_string_buffer(64), c.create_string_buffer(64)
            create_font(font, family_pointer, points, -1, False)
            try:
                font_family(font, c.byref(family_result))
                assert read_qstring(c.addressof(family_result)) == metadata['family']
                destroy_string(c.byref(family_result))
                assert font_points(font) == points
                image = c.create_string_buffer(256)
                image_size = (c.c_int * 2)(*metadata['iconSize'])
                create_image(image, image_size, 5)
                create_metrics(metrics, font, image)
                try:
                    for text in ['预制体', '派系预制体', '程序化排除区', '多边形洞口', '复合场景', '聚光灯', '植被（绘制）', 'AI 轮廓吸附']:
                        data, obj = qstring(text)
                        widths[text] = advance(metrics, c.byref(obj), -1)
                    assert max(widths.values()) <= metadata['iconSize'][0] - 4, widths
                    assert height(metrics) <= metadata['iconSize'][1] - 4
                finally:
                    destroy_metrics(metrics)
                    destroy_image(image)
                checks.append('Actual Qt font metrics fit long Chinese labels inside the expanded icon canvas')
            finally:
                destroy_font(font)
        finally:
            destroy_window(window)
    finally:
        destroy_app(app)
finally:
    k.RtlDeleteFunctionTable(table)
    k.VirtualFree(memory, 0, 0x8000)

report = {'passed': len(checks), 'failed': 0, 'checks': checks,
          'nativeCalls': 600, 'actualQtLabelWidths': widths, 'font': metadata,
          'manifestSha256': hashlib.sha256((args.build / 'patch.json').read_bytes()).hexdigest().upper()}
(ROOT / 'reports/font-tests.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
