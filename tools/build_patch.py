import argparse
import base64
import hashlib
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'python-libs'))
import pefile
pefile.MAX_IMPORT_SYMBOLS = 65536
from display_hooks import DisplayPool
import capstone


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def align(value, boundary):
    return (value + boundary - 1) // boundary * boundary


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate translation: ' + key)
        result[key] = value
    return result


def patch_module(source, translations, display_translations, shared_literals):
    original = source.read_bytes()
    pe = pefile.PE(data=original)
    assert pe.FILE_HEADER.Machine == 0x8664
    assert not pe.OPTIONAL_HEADER.DATA_DIRECTORY[4].VirtualAddress, 'Signed file requires a separate compatibility review'
    imports = {i.address - pe.OPTIONAL_HEADER.ImageBase: i.name.decode()
               for lib in pe.DIRECTORY_ENTRY_IMPORT for i in lib.imports if i.name}
    last = pe.sections[-1]
    header = last.get_file_offset() + 40
    assert header + 40 <= pe.sections[0].PointerToRawData
    assert original[header:header + 40] == bytes(40)
    assert len(original) == last.PointerToRawData + last.SizeOfRawData
    section_rva = align(last.VirtualAddress + max(last.Misc_VirtualSize, last.SizeOfRawData), pe.OPTIONAL_HEADER.SectionAlignment)
    pool = bytearray()
    locations = {}
    changes = []
    patched = bytearray(original)
    protected_ids = set(json.loads((ROOT / 'protected-identifiers.json').read_text(encoding='utf-8'))['identifiers'])

    def store_text(value):
        if value not in locations:
            locations[value] = section_rva + len(pool)
            pool.extend(value.encode('utf-8') + b'\0')
        return locations[value]

    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        raw = section.get_data()
        # QString literals can also be serialized keys; audit exclusions below.
        for match in re.finditer(rb'\xba(.{4})\x48\x8d\x0d(.{4})\xff\x15(.{4})', raw, re.S):
            rva = section.VirtualAddress + match.start()
            function = rva + 18 + struct.unpack('<i', match[3])[0]
            if 'fromAscii_helper@QString' not in imports.get(function, ''):
                continue
            length = struct.unpack('<I', match[1])[0]
            if length > 4096:
                continue
            text_rva = rva + 12 + struct.unpack('<i', match[2])[0]
            try:
                text_offset = pe.get_offset_from_rva(text_rva)
                text = original[text_offset:text_offset + length].decode('utf-8')
            except (UnicodeDecodeError, pefile.PEFormatError):
                continue
            translated = translations.get(text)
            if source.name == 'tweak_terrainmetadataeditor.modder.x64.dll' and rva == 0x1c5989:
                assert text == ', in TILESET="'
                translated = '，所属地块集="'
            if translated is None:
                continue
            # Shared tool code is restricted to the audited VFX chooser label.
            if source.name != 'tweak_terrainmetadataeditor.modder.x64.dll' and not (
                source.name == 'qttoolutility.modder.x64.dll' and (rva == 0x27fba0 or text in shared_literals)
            ):
                continue
            # These values are persisted or converted through narrow CA strings.
            # Translating them changes shortcut IDs, enums and terrain XML keys.
            internal_values = {
                'Window', 'Ungroup', 'Pan', 'Orbit', 'Move Forward', 'Move Backward',
                'Move Left', 'Move Right', 'Raise', 'Lower', 'Rotate Left', 'Rotate Right',
                'Perspective', 'Orthographic', 'Ground Plane', 'Camera Plane',
                'Height', 'Mask', 'Texture', 'Tree Colour', 'Ground Type', 'Event Area Type',
                'Circle', 'Point', 'Rectangle', 'Copy', 'Normal', 'Duplicate',
            }
            if text in internal_values:
                continue
            # Settings enum-to-string tables also feed serialization and Latin-1 UI.
            if 0x1c7d00 <= rva < 0x1c9100 or 0x1e5500 <= rva < 0x1e5800:
                continue
            # These strings also serve as shortcut, entity-factory and settings keys.
            display_only = {'Tools': {0x1cc73}, 'File': {0x19885}, 'Exit': {0x1ba34},
                            'Fullscreen': {0x1c762}, 'Debug': {0x1cfd6}, 'Camera': set()}
            if text in display_only and rva not in display_only[text]:
                continue
            if text in protected_ids and text not in display_only:
                continue
            assert original[text_offset + length] == 0
            assert sorted(re.findall(r'%[1-9n]', text)) == sorted(re.findall(r'%[1-9n]', translated))
            encoded = translated.encode('utf-8')
            translated_rva = store_text(translated)
            offset = section.PointerToRawData + match.start()
            struct.pack_into('<I', patched, offset + 1, len(encoded))
            struct.pack_into('<i', patched, offset + 8, translated_rva - (rva + 12))
            changes.append({'rva': hex(rva), 'source': text, 'translation': translated})

    # Audited display-label call sites whose constructors differ from the common pattern.
    special = {
        'tweak_terrainmetadataeditor.modder.x64.dll': [
            (0x144c26, 'Project Wizard', '工程向导', 0x144c25, 14),
            # Native open/save filters use QMetaObject::tr, bypassing both
            # QString's common constructor and Qt's painted item text.
            # Keep the wildcard byte-for-byte; these references only name
            # the file type in QTU::select_file dialogs.
            (0xf8386, 'Terry Project (*.terry)', 'Terry 工程 (*.terry)', None, None),
            (0xf95ab, 'Terry Project (*.terry)', 'Terry 工程 (*.terry)', None, None),
            # Fixed fragments in the audited display-only project composer.
            (0x1c5940, ' [has MASK]', ' [有遮罩]', None, None),
            (0x1c5947, ' [no mask]', ' [无遮罩]', None, None),
            (0x1c595e, ' [has LINKS]', ' [有连接]', None, None),
            (0x1c5965, ' [no links]', ' [无连接]', None, None),
        ],
        'qttoolutility.modder.x64.dll': [
            (0xb6403, ', with custom mesh', '，含自定义网格', None, None),
        ],
    }
    for rva, text, translated, length_rva, old_length in special.get(source.name, []):
        offset = pe.get_offset_from_rva(rva)
        assert original[offset:offset + 3] in (b'\x48\x8d\x0d', b'\x48\x8d\x15', b'\x48\x8d\x05', b'\x4c\x8d\x05')
        text_rva = rva + 7 + struct.unpack_from('<i', original, offset + 3)[0]
        text_offset = pe.get_offset_from_rva(text_rva)
        assert original[text_offset:text_offset + len(text) + 1] == text.encode() + b'\0'
        struct.pack_into('<i', patched, offset + 3, store_text(translated) - (rva + 7))
        if length_rva is not None:
            length_offset = pe.get_offset_from_rva(length_rva)
            assert original[length_offset] == old_length
            patched[length_offset] = len(translated.encode('utf-8'))
        changes.append({'rva': hex(rva), 'source': text, 'translation': translated, 'auditedDisplayLabel': True,
                        'lengthRva': hex(length_rva) if length_rva is not None else None})

    # Display sinks only: no line edits, model storage, action IDs or combo values.
    sinks = {
        '?select_file@QTU@@YA?AVQString@@PEAVQWidget@@AEBV2@11_NV?$QFlags@W4SelectFileOption@QTU@@@@@Z': 'r8',
        '?setText@QLabel@@QEAAXAEBVQString@@@Z': 'rdx',
        '??0QLabel@@QEAA@AEBVQString@@PEAVQWidget@@V?$QFlags@W4WindowType@Qt@@@@@Z': 'rdx',
        '?setToolTip@QWidget@@QEAAXAEBVQString@@@Z': 'rdx',
        '?setToolTip@QAction@@QEAAXAEBVQString@@@Z': 'rdx',
        '?setWindowTitle@QWidget@@QEAAXAEBVQString@@@Z': 'rdx',
        '?setTitle@QGroupBox@@QEAAXAEBVQString@@@Z': 'rdx',
        '?setText@QAbstractButton@@QEAAXAEBVQString@@@Z': 'rdx',
        '?setText@QAction@@QEAAXAEBVQString@@@Z': 'rdx',
        '?showText@QToolTip@@SAXAEBVQPoint@@AEBVQString@@PEAVQWidget@@@Z': 'rdx',
        '?addButton@QMessageBox@@QEAAPEAVQPushButton@@AEBVQString@@W4ButtonRole@1@@Z': 'rdx',
        '?addTab@QTabWidget@@QEAAHPEAVQWidget@@AEBVQString@@@Z': 'r8',
        '?setTabText@QTabWidget@@QEAAXHAEBVQString@@@Z': 'r8',
        '?setDetailedText@QMessageBox@@QEAAXAEBVQString@@@Z': 'rdx',
        '?setInformativeText@QMessageBox@@QEAAXAEBVQString@@@Z': 'rdx',
        '??0QMessageBox@@QEAA@W4Icon@0@AEBVQString@@1V?$QFlags@W4StandardButton@QMessageBox@@@@PEAVQWidget@@V?$QFlags@W4WindowType@Qt@@@@@Z': 'r9',
        '?drawText@QPainter@@QEAAXHHAEBVQString@@@Z': 'r9',
        '?drawText@QPainter@@QEAAXAEBVQRect@@HAEBVQString@@PEAV2@@Z': 'r9',
        '?drawText@QPainter@@QEAAXAEBVQRectF@@HAEBVQString@@PEAV2@@Z': 'r9',
        '?drawText@QPainter@@QEAAXAEBVQRectF@@AEBVQString@@AEBVQTextOption@@@Z': 'r8',
        '?drawText@QPainter@@QEAAXAEBVQPointF@@AEBVQString@@@Z': 'r8',
    }
    # Static message boxes: parent, title, body. Only substitute the const
    # display body; preserve return values, button enums and all stack arguments.
    for level in ['information', 'question', 'warning', 'critical']:
        for signature in [
            'SA?AW4StandardButton@1@PEAVQWidget@@AEBVQString@@1V?$QFlags@W4StandardButton@QMessageBox@@@@W421@@Z',
            'SAHPEAVQWidget@@AEBVQString@@1W4StandardButton@1@2@Z',
            'SAHPEAVQWidget@@AEBVQString@@1HHH@Z',
            'SA?AW4StandardButton@1@PEAVQWidget@@AEBVQString@@1W421@2@Z',
        ]:
            sinks[f'?{level}@QMessageBox@@{signature}'] = 'r8'
    if source.name == 'toolutilityqt.modder.x64.dll':
        # This additional module is scoped to nine reviewed diagnostic literals.
        # Perforce commands, state tokens, permissions and operations are intact.
        sinks = {}
    dp = DisplayPool(pool, section_rva, pe.OPTIONAL_HEADER.ImageBase)
    fragment_sites = {}
    fragments = json.loads((ROOT / 'audited-ui-fragments.json').read_text(encoding='utf-8'))
    for item in fragments.get(source.name, []):
        rva = int(item['rva'], 16)
        offset = pe.get_offset_from_rva(rva)
        instruction = original[offset:offset + 7]
        assert re.fullmatch(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d].{4}', instruction, re.S)
        data_rva = rva + 7 + struct.unpack_from('<i', instruction, 3)[0]
        text = item['source']
        assert pe.get_data(data_rva, len(text) + 1) == text.encode('ascii') + b'\0'
        translated = display_translations[text]
        new_rva = store_text(translated)
        struct.pack_into('<i', patched, offset + 3, new_rva - (rva + 7))
        if 'lengthByteRva' in item:
            length_offset = pe.get_offset_from_rva(int(item['lengthByteRva'], 16))
            assert original[length_offset] == item['lengthByte']
            new_length = len(translated.encode('utf-8')) + item.get('lengthBias', 0)
            assert 0 < new_length < 128
            patched[length_offset] = new_length
        fragment_sites[rva] = item
        changes.append({**item, 'translation': translated, 'auditedUtf8Fragment': True,
                        'translatedDataRva': hex(new_rva)})
    # QStringLiteral stores a Qt UTF-16 data header, not a UTF-8 literal.
    # These reviewed messages/undo labels are constructed BEFORE QString::arg
    # fills in paths, values and sizes. Redirect only the listed LEA operands;
    # leave the original data, argument values and all formatting calls intact.
    static_literals = json.loads((ROOT / 'audited-ui-literals.json').read_text(encoding='utf-8'))
    static_sites = {}
    for item in static_literals.get(source.name, []):
        data_rva = int(item['dataRva'], 16)
        text = item['source']
        encoded = text.encode('utf-16-le')
        expected = struct.pack('<iII4xq', -1, len(encoded) // 2, 0, 24) + encoded + b'\0\0'
        assert pe.get_data(data_rva, len(expected)) == expected, item
        translated = display_translations[text]
        new_data_rva, _ = dp.string(translated)
        assert item['references'], item
        for address in item['references']:
            rva = int(address, 16)
            offset = pe.get_offset_from_rva(rva)
            instruction = original[offset:offset + 7]
            assert re.fullmatch(rb'[\x48\x4c]\x8d[\x05\x0d\x15\x1d\x25\x2d\x35\x3d].{4}', instruction, re.S)
            assert rva + 7 + struct.unpack_from('<i', instruction, 3)[0] == data_rva, item
            struct.pack_into('<i', patched, offset + 3, new_data_rva - (rva + 7))
            static_sites[rva] = item
            changes.append({'rva': address, 'source': text, 'translation': translated,
                            'staticQStringLiteral': True, 'originalDataRva': item['dataRva'],
                            'translatedDataRva': hex(new_data_rva)})
    qt_translate = '?translate@QCoreApplication@@SA?AVQString@@PEBD00H@Z'
    qt_meta_translate = '?tr@QMetaObject@@QEBA?AVQString@@PEBD0H@Z'
    # QCommonStyle view-item layout and QItemDelegate display/size calculation.
    # Deliberately exclude QWidgetLineControl::updateDisplayText (0x13c3a7):
    # user text, filenames and editable values must retain their exact display.
    item_layout_calls = {0x9489a, 0x95444, 0x252020, 0x252248, 0x25402a} if source.name == 'Qt5Widgets.dll' else set()
    display_calls = {0x2d2600, 0x2d2d42} if source.name == 'qttoolutility.modder.x64.dll' else set()
    # QString::arg for the selection-status label only; schema uses of
    # "entity" elsewhere must remain unchanged.
    status_argument_calls = {
        'tweak_terrainmetadataeditor.modder.x64.dll': {0x172f80},
        # ProjectTile/ProjectTileMap::description compose UI text with dimensions.
        # Translate only the database name passed to QString::arg, before the
        # numeric width/height substitutions; project database enums are untouched.
        'qttoolutility.modder.x64.dll': {0xb6339, 0xda692},
    }.get(source.name, set())
    # Project title/status and open-project summary composers only. Translate
    # name/description fragments before formatting (including <b>...</b><br>),
    # leaving the project component, user filename and stored IDs intact.
    title_fragment_calls = {0x1c572f, 0x1c583b, 0x1c57b6, 0x1573f6, 0x157462,
                            0x13d53f, 0x13d5c3} if source.name == 'tweak_terrainmetadataeditor.modder.x64.dll' else set()
    paint_display = dict(display_translations)
    paint_display.update({s.upper(): t for s, t in display_translations.items() if len(s) <= 60 and '%' not in s})
    candidates = {}
    for section in pe.sections:
        if not section.Characteristics & 0x20000000:
            continue
        for match in re.finditer(rb'\xff[\x15\x25](.{4})', section.get_data(), re.S):
            rva = section.VirtualAddress + match.start()
            iat = rva + 6 + struct.unpack('<i', match[1])[0]
            name = imports.get(iat, '')
            if rva in item_layout_calls:
                assert name.startswith(('??0QTextLayout@@', '?setText@QTextLayout@@'))
            if rva in status_argument_calls:
                assert name == '?arg@QString@@QEBA?AV1@AEBV1@HVQChar@@@Z'
            if rva in title_fragment_calls:
                assert name == ('??4QString@@QEAAAEAV0@$$QEAV0@@Z' if rva == 0x1c57b6 else '?append@QString@@QEAAAEAV1@AEBV1@@Z')
            if name in sinks or (source.name == 'Qt5Widgets.dll' and name in (qt_translate, qt_meta_translate)) or rva in display_calls or rva in item_layout_calls or rva in status_argument_calls or rva in title_fragment_calls:
                candidates[rva] = (iat, name, match.group()[1] == 0x25)
    # Validate instruction boundaries against the x64 runtime function table.
    validated = set()
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    for entry in pe.DIRECTORY_ENTRY_EXCEPTION:
        begin, end = entry.struct.BeginAddress, entry.struct.EndAddress
        relevant = [r for r in candidates.keys() | static_sites.keys() | fragment_sites.keys() if begin <= r < end]
        if relevant:
            addresses = {addr for addr, size, mnemonic, operands in md.disasm_lite(pe.get_data(begin, end - begin), begin)}
            validated.update(set(relevant) & addresses)
    hooks = {}
    assert static_sites.keys() <= validated, 'Static UI literal is not at an instruction boundary'
    assert fragment_sites.keys() <= validated, 'UTF-8 UI fragment is not at an instruction boundary'
    for rva in sorted(validated & candidates.keys()):
        iat, name, is_jump = candidates[rva]
        kind = ('latin1-return' if rva in display_calls else 'translate-return' if name == qt_translate
                else 'meta-translate-return' if name == qt_meta_translate else 'qstring-argument')
        argument = 'r8' if rva in status_argument_calls else sinks.get(name, 'rdx')
        if rva == 0x1c57b6 and rva in title_fragment_calls:
            # A static translated QString must never be passed as a move source.
            # Use the imported const-reference assignment at this one display
            # temporary. Qt retains/releases its data; the source is destroyed
            # by the existing caller, as before.
            iat = next(k for k, v in imports.items() if v == '??4QString@@QEAAAEAV0@AEBV0@@Z')
        key = (iat, kind, argument)
        if key not in hooks:
            dictionary = paint_display if name.startswith('?drawText@') or rva in item_layout_calls else display_translations
            hooks[key] = dp.make_hook(dictionary, iat, kind, argument)
        offset = pe.get_offset_from_rva(rva)
        patched[offset:offset + 6] = (b'\xe9' if is_jump else b'\xe8') + struct.pack('<i', hooks[key] - (rva + 5)) + b'\x90'
        changes.append({'rva': hex(rva), 'displayHook': name, 'kind': kind, 'argument': argument})
    assert display_calls <= validated, 'Property label hook no longer matches this build'
    assert item_layout_calls <= validated, 'View-item display hook no longer matches this build'
    assert status_argument_calls <= validated, 'Selection status hook no longer matches this build'
    assert title_fragment_calls <= validated, 'Project title composer no longer matches this build'
    executable_pool = bool(hooks)
    if dp.relocations:
        directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[5]
        reloc_rva, reloc_size = dp.relocation_table(pe.get_data(directory.VirtualAddress, directory.Size))
        struct.pack_into('<II', patched, directory.get_file_offset(), reloc_rva, reloc_size)
    if not changes:
        return None
    raw_size = align(len(pool), pe.OPTIONAL_HEADER.FileAlignment)
    new_section = struct.pack('<8sIIIIIIHHI', b'.terrycn', len(pool), section_rva, raw_size,
                              len(original), 0, 0, 0, 0, 0x60000060 if executable_pool else 0x40000040)
    patched[header:header + 40] = new_section
    struct.pack_into('<H', patched, pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'), len(pe.sections) + 1)
    struct.pack_into('<I', patched, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'),
                     align(section_rva + len(pool), pe.OPTIONAL_HEADER.SectionAlignment))
    struct.pack_into('<I', patched, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfInitializedData'),
                     pe.OPTIONAL_HEADER.SizeOfInitializedData + raw_size)
    patched.extend(pool + bytes(raw_size - len(pool)))
    final_pe = pefile.PE(data=bytes(patched))
    struct.pack_into('<I', patched, pe.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'), final_pe.generate_checksum())
    # The delivery contains only differences, never the proprietary DLL.
    edits = []
    index = 0
    while index < len(original):
        if original[index] == patched[index]:
            index += 1
            continue
        start = index
        while index < len(original) and original[index] != patched[index]:
            index += 1
        edits.append({'offset': start, 'before': base64.b64encode(original[start:index]).decode(),
                      'after': base64.b64encode(patched[start:index]).decode()})
    record = {'path': 'binaries/' + source.name, 'originalSha256': sha(original), 'patchedSha256': sha(patched),
              'originalLength': len(original), 'patchedLength': len(patched), 'edits': edits,
              'append': base64.b64encode(patched[len(original):]).decode()}
    return bytes(patched), record, changes, dp.hooks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    expected = json.loads((ROOT / 'source-hashes.json').read_text(encoding='utf-8'))
    for name, digest in expected.items():
        assert sha((args.source / name).read_bytes()) == digest, 'Unsupported source version: ' + name
    translations = json.loads((ROOT / 'translations.zh-CN.json').read_text(encoding='utf-8-sig'), object_pairs_hook=unique_json)
    additions = json.loads((ROOT / 'translations.ui.zh-CN.json').read_text(encoding='utf-8'), object_pairs_hook=unique_json)
    assert not set(additions) & set(translations), 'Duplicate literal translation across dictionaries'
    translations.update(additions)
    messages = json.loads((ROOT / 'translations.messages.zh-CN.json').read_text(encoding='utf-8'), object_pairs_hook=unique_json)
    assert not set(messages) & set(translations), 'Duplicate message translation across dictionaries'
    translations.update(messages)
    display = dict(translations)
    display.update(json.loads((ROOT / 'translations.display.zh-CN.json').read_text(encoding='utf-8'), object_pairs_hook=unique_json))
    properties = json.loads((ROOT / 'translations.properties.zh-CN.json').read_text(encoding='utf-8'), object_pairs_hook=unique_json)
    assert not set(properties) & set(display), 'Duplicate property translation across dictionaries'
    display.update(properties)
    for filename in ['translations.extended.zh-CN.json', 'translations.engine.zh-CN.json', 'translations.templates.zh-CN.json']:
        extra = json.loads((ROOT / filename).read_text(encoding='utf-8'), object_pairs_hook=unique_json)
        assert not set(extra) & set(display), f'Duplicate translation in {filename}: {set(extra) & set(display)}'
        display.update(extra)
    for source, translated in display.items():
        assert sorted(re.findall(r'%L?\d+|%n', source)) == sorted(re.findall(r'%L?\d+|%n', translated)), source
    args.output.mkdir(parents=True, exist_ok=True)
    records, report, hook_report = [], {}, {}
    for name in ['tweak_terrainmetadataeditor.modder.x64.dll', 'qttoolutility.modder.x64.dll', 'Qt5Widgets.dll', 'toolutilityqt.modder.x64.dll']:
        result = patch_module(args.source / name, translations, display, set(messages) | set(additions))
        if result:
            binary, record, changes, hooks = result
            (args.output / name).write_bytes(binary)
            records.append(record)
            report[name] = changes
            hook_report[name] = hooks
    tooltip_original = (args.source / 'status_tooltips.xml').read_bytes()
    tooltip_tree = ET.fromstring(tooltip_original)
    tooltip_translations = json.loads((ROOT / 'status-tooltips.zh-CN.json').read_text(encoding='utf-8'), object_pairs_hook=unique_json)
    tooltip_count = 0
    for element in tooltip_tree.iter('tooltip'):
        key = element.get('tool', '')
        assert key in tooltip_translations, key
        element.text = tooltip_translations[key]
        tooltip_count += 1
    tooltip_result = ET.tostring(tooltip_tree, encoding='utf-8', xml_declaration=True)
    (args.output / 'status_tooltips.xml').write_bytes(tooltip_result)
    records.append({'path': 'working_data/Terry/status_tooltips.xml', 'originalSha256': sha(tooltip_original),
                    'patchedSha256': sha(tooltip_result), 'originalLength': len(tooltip_original),
                    'patchedLength': len(tooltip_result), 'replacement': base64.b64encode(tooltip_result).decode()})
    previous = json.loads((ROOT / 'patch.json').read_text(encoding='utf-8'))
    for record in records:
        older = next((r for r in previous['files'] if r['path'] == record['path']), None)
        if older and older['originalSha256'] == record['originalSha256']:
            record['previousPatchedSha256'] = sorted(set(older.get('previousPatchedSha256', []) + [older['patchedSha256']]) - {record['patchedSha256']})
    (args.output / 'patch.json').write_text(json.dumps({'format': 1, 'version': '2026-10-10 R5', 'files': records}, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output / 'coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output / 'display-hooks.json').write_text(json.dumps(hook_report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'files': len(records), 'displaySites': sum(len(v) for v in report.values()),
                      'literalStrings': len(set(x['source'] for v in report.values() for x in v if 'source' in x)),
                      'displayDictionary': len(display), 'tooltips': tooltip_count}, ensure_ascii=False))


if __name__ == '__main__':
    main()
