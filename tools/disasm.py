import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / 'python-libs'))
import pefile
pefile.MAX_IMPORT_SYMBOLS = 65536
import capstone

pe = pefile.PE(sys.argv[1])
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
md.detail = True
imports = {i.address - pe.OPTIONAL_HEADER.ImageBase: i.name.decode() for lib in pe.DIRECTORY_ENTRY_IMPORT for i in lib.imports if i.name}
start = int(sys.argv[2], 0)
size = int(sys.argv[3], 0)
for ins in md.disasm(pe.get_data(start, size), start):
    extra = ''
    for op in ins.operands:
        if op.type == capstone.x86.X86_OP_MEM and op.mem.base == capstone.x86.X86_REG_RIP:
            target = ins.address + ins.size + op.mem.disp
            if target in imports:
                extra += ' ' + imports[target]
            elif ins.mnemonic == 'lea':
                try:
                    data = pe.get_data(target, 100).split(b'\0')[0]
                    if len(data) > 1:
                        extra += ' ' + repr(data.decode())
                except Exception:
                    pass
    print(f'{ins.address:08x} {ins.mnemonic:7s} {ins.op_str}{extra}')
