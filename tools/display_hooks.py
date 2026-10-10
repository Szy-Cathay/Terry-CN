"""Windows x64 leaf shims for display-only Qt 5 arguments.

No original QString/CA::String is mutated. All argument registers and stack
arguments survive, except the explicitly selected const QString& argument.
Unmatched text goes straight to the original imported function. Static QString
objects use IMAGE_REL_BASED_DIR64 relocations so ASLR remains enabled.
"""
import struct
from collections import defaultdict


class Code:
    def __init__(self, rva):
        self.rva, self.data, self.labels, self.fixups = rva, bytearray(), {}, []

    def emit(self, value):
        self.data.extend(value)

    def label(self, name):
        self.labels[name] = len(self.data)

    def branch(self, opcode, label):
        self.emit(opcode)
        self.fixups.append((len(self.data), label))
        self.emit(bytes(4))

    def rip(self, opcode, target):
        self.emit(opcode)
        self.emit(struct.pack('<i', target - (self.rva + len(self.data) + 4)))

    def finish(self):
        for offset, label in self.fixups:
            struct.pack_into('<i', self.data, offset, self.labels[label] - offset - 4)
        return self.data


class DisplayPool:
    def __init__(self, pool, rva, imagebase):
        self.pool, self.rva, self.imagebase = pool, rva, imagebase
        self.strings, self.relocations = {}, []
        self.hooks = []

    def align(self, alignment=16):
        self.pool.extend(bytes((-len(self.pool)) % alignment))
        return self.rva + len(self.pool)

    def string(self, text):
        if text not in self.strings:
            data_rva = self.align(8)
            value = text.encode('utf-16-le')
            self.pool.extend(struct.pack('<iII4xq', -1, len(value) // 2, 0, 24) + value + b'\0\0')
            obj_rva = self.align(8)
            self.pool.extend(struct.pack('<Q', self.imagebase + data_rva))
            self.relocations.append(obj_rva)
            self.strings[text] = (data_rva, obj_rva)
        return self.strings[text]

    def make_hook(self, translations, original_iat, kind, argument='rdx'):
        """Display arguments or Qt static/member translation return conventions."""
        mapping = {s: self.string(t) for s, t in translations.items() if s and s != t}
        start = self.align()
        c = Code(start)
        if kind == 'qstring-argument':
            c.emit({'rdx': b'\x4c\x8b\xd2', 'r8': b'\x4d\x8b\xd0', 'r9': b'\x4d\x8b\xd1'}[argument])
            c.emit(b'\x4d\x85\xd2') # test r10,r10
            c.branch(b'\x0f\x84', 'fallback')
            c.emit(b'\x4d\x8b\x12\x45\x8b\x5a\x04\x49\x8b\x42\x10\x4c\x03\xd0')
            groups = defaultdict(list)
            for source, value in mapping.items():
                groups[len(source.encode('utf-16-le')) // 2].append((source, value))
            for size, group in sorted(groups.items()):
                c.emit(b'\x41\x81\xfb' + struct.pack('<I', size))
                c.branch(b'\x0f\x85', f'group-{size}')
                for index, (source, (data_rva, obj_rva)) in enumerate(group):
                    target = f'miss-{size}-{index}'
                    value = source.encode('utf-16-le')
                    for offset in range(0, len(value) // 4 * 4, 4):
                        c.emit(b'\x41\x81\xba' + struct.pack('<I', offset) + value[offset:offset + 4])
                        c.branch(b'\x0f\x85', target)
                    if len(value) % 4:
                        c.emit(b'\x66\x41\x81\xba' + struct.pack('<I', len(value) - 2) + value[-2:])
                        c.branch(b'\x0f\x85', target)
                    c.rip({'rdx': b'\x48\x8d\x15', 'r8': b'\x4c\x8d\x05', 'r9': b'\x4c\x8d\x0d'}[argument], obj_rva)
                    c.branch(b'\xe9', 'fallback')
                    c.label(target)
                c.branch(b'\xe9', 'fallback')
                c.label(f'group-{size}')
        else:
            c.emit(b'\x4c\x8b\xd2' if kind == 'latin1-return' else b'\x4d\x8b\xd0')
            c.emit(b'\x4d\x85\xd2')
            c.branch(b'\x0f\x84', 'fallback')
            for index, (source, (data_rva, obj_rva)) in enumerate(mapping.items()):
                if not source.isascii():
                    continue
                target = f'miss-{index}'
                if kind == 'latin1-return':
                    # Match only the NUL-terminated API form used by these audited
                    # sites. Explicit-length slices must keep original semantics.
                    c.emit(b'\x41\x83\xf8\xff')
                    c.branch(b'\x0f\x85', 'fallback')
                for offset, value in enumerate(source.encode('ascii') + b'\0'):
                    c.emit(b'\x41\x80\xba' + struct.pack('<I', offset) + bytes([value]))
                    c.branch(b'\x0f\x85', target)
                c.rip(b'\x48\x8d\x05', data_rva)
                # QCoreApplication::translate is static: hidden result in rcx.
                # QMetaObject::tr is a member: rcx=this, hidden result in rdx.
                c.emit(b'\x48\x89\x02\x48\x89\xd0\xc3' if kind == 'meta-translate-return'
                       else b'\x48\x89\x01\x48\x89\xc8\xc3')
                c.label(target)
        c.label('fallback')
        c.rip(b'\xff\x25', original_iat)
        self.pool.extend(c.finish())
        self.hooks.append({'rva': hex(start), 'kind': kind, 'argument': argument,
                           'iatRva': hex(original_iat), 'strings': len(mapping)})
        return start

    def relocation_table(self, original):
        start = self.align(4)
        self.pool.extend(original)
        pages = defaultdict(list)
        for rva in self.relocations:
            pages[rva & ~4095].append((10 << 12) | (rva & 4095))
        for page, entries in sorted(pages.items()):
            if len(entries) % 2:
                entries.append(0)
            self.pool.extend(struct.pack('<II', page, 8 + len(entries) * 2))
            self.pool.extend(struct.pack('<' + 'H' * len(entries), *entries))
        return start, self.rva + len(self.pool) - start
