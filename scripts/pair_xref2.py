#!/usr/bin/env python3
"""pair_xref2.py — 正确的 lui(低16位=hi) + addiu/ori(同寄存器, lo) 配对引用查找。
用法: python pair_xref2.py <elf> <字符串文件偏移> [引用数上限]
"""
import struct
import sys

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS64
from elftools.elf.elffile import ELFFile


def main():
    elf_path, str_off = sys.argv[1], int(sys.argv[2], 0)
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 8
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
    print(f"目标 VA {va:#x}: lui_imm={hi:#x}, lo={lo:#x}")

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
        if (w >> 26) == 0x0F and (w & 0xFFFF) == hi:  # lui rt, hi  (立即数在低16位!)
            rt = (w >> 16) & 0x1F
            for k in range(1, 13):
                j = idx[a] + k
                if j >= len(addrs):
                    break
                b = addrs[j]
                w2 = insns[b]
                op2 = w2 >> 26
                rs2 = (w2 >> 21) & 0x1F
                rt2 = (w2 >> 16) & 0x1F
                imm2 = w2 & 0xFFFF
                if rs2 == rt and imm2 == lo and op2 in (0x09, 0x0D):
                    hits.append((a, b))
                    break
                # rt 被写坏则放弃
                if rt2 == rt and not (op2 == 0 and (w2 & 0x3F) == 0x25 and rs2 == 0):
                    break
    print(f"精确引用: {len(hits)} 处")
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64)
    for a, b in hits[:limit]:
        print(f"\n===== lui@{a:#x} + lo@{b:#x} =====")
        lo_off = None
        for o, s, v in loads:
            if v <= a < v + s:
                lo_off = o + (a - v)
                break
        start = a - 0x80
        for x in range(start, b + 0x80, 4):
            w = insns.get(x)
            if w is None:
                continue
            for insn in md.disasm(struct.pack("<I", w), x):
                mark = ""
                if x == a:
                    mark = "  <== lui"
                elif x == b:
                    mark = "  <== lo"
                print(f"  {x:#010x}: {w:08x} {insn.mnemonic:<8} {insn.op_str}{mark}")
                break


if __name__ == "__main__":
    main()
