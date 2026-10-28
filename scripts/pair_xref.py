#!/usr/bin/env python3
"""pair_xref.py — 精确查找 lui hi + ori/addiu lo 同寄存器配对的地址引用（LE MIPS32R5900）。
用法: python pair_xref.py <elf> <字符串文件偏移>
"""
import struct
import sys

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS64
from elftools.elf.elffile import ELFFile


def main():
    elf_path, str_off = sys.argv[1], int(sys.argv[2], 0)
    data = open(elf_path, "rb").read()
    f = open(elf_path, "rb")
    elf = ELFFile(f)
    loads = [(seg.header.p_offset, seg.header.p_filesz, seg.header.p_vaddr)
             for seg in elf.iter_segments() if seg.header.p_type == "PT_LOAD"]

    def off2va(off):
        for o, s, v in loads:
            if o <= off < o + s:
                return v + (off - o)

    va = off2va(str_off)
    hi = ((va + 0x8000) >> 16) & 0xFFFF
    lo = va & 0xFFFF
    print(f"目标 VA {va:#x}: lui={hi:#x}, lo={lo:#x}")

    # 预取全部指令 (VA -> word)
    insns = {}
    for o, s, v in loads:
        seg = data[o:o + s]
        for i in range(len(seg) // 4):
            insns[v + i * 4] = struct.unpack_from("<I", seg, i * 4)[0]
    addrs = sorted(insns)
    idx = {a: i for i, a in enumerate(addrs)}

    hits = []
    for a in addrs:
        w = insns[a]
        if (w >> 26) == 0x0F and ((w >> 16) & 0x1F) == hi:  # lui rt, hi
            rt = (w >> 21) & 0x1F
            # 向后看 10 条
            for k in range(1, 11):
                b = addrs[idx[a] + k] if idx[a] + k < len(addrs) else None
                if b is None:
                    break
                w2 = insns[b]
                op2 = w2 >> 26
                rs2 = (w2 >> 21) & 0x1F
                rt2 = (w2 >> 16) & 0x1F
                imm2 = w2 & 0xFFFF
                if rs2 == rt and rt2 == rt and imm2 == lo and op2 in (0x09, 0x0D):  # addiu/ori rt, rt, lo
                    hits.append((a, b))
                    break
                # 寄存器被覆盖则放弃
                if rt2 == rt and op2 not in (0,):  # 跳过 nop
                    if not (op2 == 0 and (w2 & 0x3F) == 0x25):  # or r,r,0 = move
                        break
    print(f"精确引用: {len(hits)}")
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64)
    for a, b in hits[:10]:
        print(f"\n===== 引用 @ {a:#x} =====")
        start = a - 0x60
        for va2 in [x for x in addrs if a - 0x60 <= x <= b + 0x60]:
            w = insns[va2]
            # 手工解码几条常见的
            for insn in md.disasm(struct.pack("<I", w), va2):
                mark = " <<<" if va2 in (a, b) else ""
                print(f"  {va2:#010x}: {w:08x} {insn.mnemonic:<8} {insn.op_str}{mark}")
                break


if __name__ == "__main__":
    main()
