"""Audited Terry-only typography changes; no global Qt font replacement."""
import struct

from display_hooks import Code

FONT_FAMILY = 'Microsoft YaHei UI'
ICON_POINT_SIZE = 9
ICON_SIZE = (112, 32)
MENU_STYLESHEET = '''
QMenuBar, QMenu { font-family: "Microsoft YaHei UI"; font-size: 10pt; font-weight: normal; }
QMenuBar::item { padding: 3px 8px; }
QMenu::item { padding: 4px 24px 4px 24px; }
QToolBar { spacing: 1px; }
QToolBar QToolButton { font-family: "Microsoft YaHei UI"; font-size: 9pt; font-weight: normal; padding: 3px 1px; }
'''.strip()


def make_menu_hook(dp, stylesheet_iat, menubar_iat):
    """Set a scoped main-window stylesheet, then tail-call menuBar(this).

    The original accessor has only its this argument. Save it across Qt's
    stylesheet call, reserve the Windows x64 shadow space, and keep the stack
    aligned. The caller receives the original menuBar return value unchanged.
    """
    _, text = dp.string(MENU_STYLESHEET)
    start = dp.align()
    code = Code(start)
    code.emit(b'\x48\x83\xec\x28')          # sub rsp,40
    code.emit(b'\x48\x89\x4c\x24\x20')  # save this above shadow space
    code.rip(b'\x48\x8d\x15', text)       # rdx = const QString&
    code.rip(b'\xff\x15', stylesheet_iat)
    code.emit(b'\x48\x8b\x4c\x24\x20')
    code.emit(b'\x48\x83\xc4\x28')
    code.rip(b'\xff\x25', menubar_iat)
    dp.pool.extend(code.finish())
    end = dp.rva + len(dp.pool)
    unwind = dp.align(4)
    # UNWIND_INFO: version 1, 4-byte prologue, UWOP_ALLOC_SMALL(40).
    dp.pool.extend(bytes.fromhex('01 04 01 00 04 42 00 00'))
    return start, end, unwind


def apply_font_patch(pe, patched, dp):
    changes = []

    def replace(rva, before, after, purpose):
        assert len(before) == len(after)
        offset = pe.get_offset_from_rva(rva)
        assert bytes(patched[offset:offset + len(before)]) == before, purpose
        patched[offset:offset + len(after)] = after
        changes.append({'rva': hex(rva), 'fontUi': True, 'purpose': purpose,
                        'beforeHex': before.hex(), 'afterHex': after.hex()})

    # The dedicated text-icon font is constructed once from a static QString.
    # Leave Helvetica's original data and all unrelated fonts untouched.
    _, family = dp.string(FONT_FAMILY)
    rva = 0x28034a
    before = bytes.fromhex('48 8d 15 a7 56 6c 00')
    replace(rva, before, before[:3] + struct.pack('<i', family - (rva + 7)),
            'Text-icon font family: Helvetica -> Microsoft YaHei UI')
    replace(0x280346, bytes.fromhex('45 8d 41 08'),
            b'\x45\x8d\x41' + bytes([ICON_POINT_SIZE + 1]),
            f'Text-icon point size: 7 -> {ICON_POINT_SIZE}; default weight preserved')

    # The same QSize accessor serves text-icon creation and toolbar iconSize.
    size = dp.align(8)
    dp.pool.extend(struct.pack('<ii', *ICON_SIZE))
    before = bytes.fromhex('48 8b 05 51 be 47 00')
    replace(0x1ffb50, before, before[:3] + struct.pack('<i', size - 0x1ffb57),
            f'Text-icon and toolbar canvas: 64x32 -> {ICON_SIZE[0]}x{ICON_SIZE[1]}')
    replace(0x244226, bytes.fromhex('c7 45 30 20 00 00 00'),
            b'\xc7\x45\x30' + struct.pack('<i', ICON_SIZE[0]),
            'Snap AI text-icon canvas: allow its full Chinese label')

    imports = {i.address - pe.OPTIONAL_HEADER.ImageBase: i.name.decode()
               for library in pe.DIRECTORY_ENTRY_IMPORT for i in library.imports if i.name}
    assert imports[0x64e1c0] == '?setStyleSheet@QWidget@@QEAAXAEBVQString@@@Z'
    assert imports[0x64e708] == '?menuBar@QMainWindow@@QEBAPEAVQMenuBar@@XZ'
    function = make_menu_hook(dp, 0x64e1c0, 0x64e708)
    rva = 0x19849
    replace(rva, bytes.fromhex('ff 15 b9 4e 63 00'),
            b'\xe8' + struct.pack('<i', function[0] - rva - 5) + b'\x90',
            'MainWindow menu initialization: scoped menu/toolbar typography')

    # Register the non-leaf hook in the PE exception directory. All original
    # runtime functions and unwind records remain byte-for-byte intact.
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    original = pe.get_data(directory.VirtualAddress, directory.Size)
    assert directory.Size % 12 == 0
    assert struct.unpack_from('<I', original, len(original) - 12)[0] < function[0]
    table = dp.align(4)
    dp.pool.extend(original + struct.pack('<III', *function))
    struct.pack_into('<II', patched, directory.get_file_offset(), table, len(original) + 12)
    metadata = {'family': FONT_FAMILY, 'iconPointSize': ICON_POINT_SIZE,
                'iconSize': list(ICON_SIZE), 'stylesheet': MENU_STYLESHEET,
                'menuHook': {'beginRva': hex(function[0]), 'endRva': hex(function[1]),
                             'unwindRva': hex(function[2])},
                'exceptionTableRva': hex(table)}
    return changes, metadata
