import sys, struct
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_LITTLE_ENDIAN

BASE = 0x0023CD60
with open("work/elf/PSU.elf", "rb") as f:
    elf = f.read()

regs = ['zero', 'at', 'v0', 'v1', 'a0', 'a1', 'a2', 'a3',
        't0', 't1', 't2', 't3', 't4', 't5', 't6', 't7',
        's0', 's1', 's2', 's3', 's4', 's5', 's6', 's7',
        't8', 't9', 'k0', 'k1', 'gp', 'sp', 'fp', 'ra']

def disasm_mips(code, va):
    op = code >> 26
    rs = (code >> 21) & 0x1f
    rt = (code >> 16) & 0x1f
    rd = (code >> 11) & 0x1f
    sa = (code >> 6) & 0x1f
    fn = code & 0x3f
    imm = code & 0xffff
    simm = imm - 0x10000 if imm >= 0x8000 else imm
    if code == 0: return 'nop'
    if op == 0:
        if fn == 0x20: return f'add ${regs[rd]}, ${regs[rs]}, ${regs[rt]}'
        if fn == 0x21: return f'addu ${regs[rd]}, ${regs[rs]}, ${regs[rt]}'
        if fn == 0x24: return f'and ${regs[rd]}, ${regs[rs]}, ${regs[rt]}'
        if fn == 0x25: return f'or ${regs[rd]}, ${regs[rs]}, ${regs[rt]}'
        if fn == 0x2A: return f'slt ${regs[rd]}, ${regs[rs]}, ${regs[rt]}'
        if fn == 0x2D:
            if rt == 0: return f'move ${regs[rd]}, ${regs[rs]}'
            return f'daddu ${regs[rd]}, ${regs[rs]}, ${regs[rt]}'
        if fn == 0x00: return f'sll ${regs[rd]}, ${regs[rt]}, {sa}'
        if fn == 0x02: return f'srl ${regs[rd]}, ${regs[rt]}, {sa}'
        if fn == 0x03: return f'sra ${regs[rd]}, ${regs[rt]}, {sa}'
        if fn == 0x08: return f'jr ${regs[rs]}'
        if fn == 0x09: return f'jalr ${regs[rd]}, ${regs[rs]}'
        return f'special fn=0x{fn:02x} rd={regs[rd]} rs={regs[rs]} rt={regs[rt]}'
    if op == 0x09: return f'addiu ${regs[rt]}, ${regs[rs]}, {simm}'
    if op == 0x0A: return f'slti ${regs[rt]}, ${regs[rs]}, {simm}'
    if op == 0x0B: return f'sltiu ${regs[rt]}, ${regs[rs]}, {simm}'
    if op == 0x0C: return f'andi ${regs[rt]}, ${regs[rs]}, 0x{imm:04x}'
    if op == 0x0D: return f'ori ${regs[rt]}, ${regs[rs]}, 0x{imm:04x}'
    if op == 0x0F: return f'lui ${regs[rt]}, 0x{imm:04x}'
    if op == 0x04: return f'beq ${regs[rs]}, ${regs[rt]}, 0x{va + 4 + simm*4:08x}'
    if op == 0x05: return f'bne ${regs[rs]}, ${regs[rt]}, 0x{va + 4 + simm*4:08x}'
    if op == 0x01:
        if rt == 0: return f'bltz ${regs[rs]}, 0x{va + 4 + simm*4:08x}'
        if rt == 1: return f'bgez ${regs[rs]}, 0x{va + 4 + simm*4:08x}'
        if rt == 2: return f'bltzl ${regs[rs]}, 0x{va + 4 + simm*4:08x}'
        if rt == 3: return f'bgezl ${regs[rs]}, 0x{va + 4 + simm*4:08x}'
    if op == 0x06: return f'blez ${regs[rs]}, 0x{va + 4 + simm*4:08x}'
    if op == 0x07: return f'bgtz ${regs[rs]}, 0x{va + 4 + simm*4:08x}'
    if op == 0x14: return f'beql ${regs[rs]}, ${regs[rt]}, 0x{va + 4 + simm*4:08x}'
    if op == 0x15: return f'bnel ${regs[rs]}, ${regs[rt]}, 0x{va + 4 + simm*4:08x}'
    if op == 0x02: return f'j 0x{(code & 0x3FFFFFF)*4:08x}'
    if op == 0x03: return f'jal 0x{(code & 0x3FFFFFF)*4:08x}'
    if op == 0x20: return f'lb ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x23: return f'lw ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x24: return f'lbu ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x25: return f'lhu ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x28: return f'sb ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x29: return f'sh ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x2B: return f'sw ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x18: return f'daddiu ${regs[rt]}, ${regs[rs]}, {simm}'
    if op == 0x19: return f'daddiu ${regs[rt]}, ${regs[rs]}, {simm}'
    if op == 0x1F: return f'sd ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x1E: return f'ld ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x3F: return f'sq ${regs[rt]}, {simm}(${regs[rs]})'
    if op == 0x37: return f'lq ${regs[rt]}, {simm}(${regs[rs]})'
    return f'raw op=0x{op:02x} (0x{code:08x})'

def dump(title, file_start, length):
    print(f"\n=======================================================")
    print(f"{title} (File: 0x{file_start:06X}, EE VA: 0x{BASE+file_start:08X})")
    print(f"=======================================================")
    for pos in range(file_start, file_start + length, 4):
        raw = struct.unpack('<I', elf[pos:pos+4])[0]
        va = BASE + pos
        print(f"0x{va:08X} (File 0x{pos:06X}): {disasm_mips(raw, va):35s} (0x{raw:08X})")

if __name__ == '__main__':
    # 1. 伤害分发上下文 (0x00445580 ~ 0x00445650)
    dump("Damage Dispatch Context (0x00445580 ~ 0x00445640)", 0x00208820, 0xC0)

    # 2. HP/扣血函数 (0x0029D790 ~ 0x0029D840)
    dump("Target Function 0x00060A40 / 0x0029D790 (HP Delta / Deduct)", 0x00060A30, 0xC0)

    # 3. 金钱函数 (0x0029A000 ~ 0x0029A080)
    dump("Money Add Function (0x0029A000 ~ 0x0029A080)", 0x0005D2A0, 0x80)
