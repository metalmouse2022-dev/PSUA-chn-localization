#!/usr/bin/env python3
"""xref_str.py — 在 PS2 EE ELF (LE MIPS) 中交叉引用字符串：
1) 扫描代码中的 lui/ori/addiu/lw 立即数引用
2) 扫描数据中的 32 位小端指针引用（指针表）
用法: python xref_str.py <elf> <字符串文件偏移>
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
    print(f"str_off {str_off:#x} -> VA {va:#x}")

    # --- 1. 立即数引用 (lui hi / ori|addiu lo) ---
    hi = ((va + 0x8000) >> 16) & 0xFFFF
    lo = va & 0xFFFF
    hits = []
    for o, s, v in loads:
        seg = data[o:o + s]
        n = len(seg) // 4
        for i in range(n):
            w = struct.unpack_from("<I", seg, i * 4)[0]
            op = w >> 26
            imm = w & 0xFFFF
            if imm == lo and op in (0x9, 0xD, 0x23, 0x2B, 0x35, 0x3F, 0x28, 0x25):  # addiu ori lw sw lhu sh lwl lwu
                hits.append(v + i * 4)
    print(f"lo=imm 引用: {[hex(h) for h in hits[:20]]} (共{len(hits)})")

    # --- 2. 数据指针引用 ---
    ptr = struct.pack("<I", va)
    ptr_hits = []
    pos = data.find(ptr)
    while pos >= 0 and len(ptr_hits) < 20:
        ptr_hits.append(pos)
        pos = data.find(ptr, pos + 1)
    print(f"指针表引用 (文件偏移): {[hex(h) for h in ptr_hits]}")

    # --- 反汇编每个引用点上下文 ---
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64)
    targets = [h for h in hits]
    for ref_va in targets[:8]:
        print(f"\n===== 引用 VA {ref_va:#x} 上下文 =====")
        for o, s, v in loads:
            if v <= ref_va < v + s:
                start = ref_va - 0x100
                fo = o + (start - v)
                code = data[fo:fo + 0x200]
                for insn in md.disasm(code, start):
                    mark = " <<<" if insn.address == ref_va else ""
                    print(f"  {insn.address:#010x}: {insn.mnemonic:<8} {insn.op_str}{mark}")
                    if insn.address >= ref_va + 0x60:
                        break
                break

    # 指针表引用者: 找谁引用了这些指针槽的地址
    for poff in ptr_hits[:6]:
        pva = off2va(poff)
        if pva is None:
            continue
        phi = ((pva + 0x8000) >> 16) & 0xFFFF
        plo = pva & 0xFFFF
        refs = []
        for o, s, v in loads:
            seg = data[o:o + s]
            n = len(seg) // 4
            for i in range(n):
                w = struct.unpack_from("<I", seg, i * 4)[0]
                op = w >> 26
                if (w & 0xFFFF) == plo and op in (0x9, 0xD):
                    refs.append(v + i * 4)
        print(f"\n指针槽 {pva:#x} (hi={phi:#x} lo={plo:#x}) 被引用: {[hex(r) for r in refs[:8]]}")
        for ref_va in refs[:4]:
            for o, s, v in loads:
                if v <= ref_va < v + s:
                    start = ref_va - 0x80
                    fo = o + (start - v)
                    code = data[fo:fo + 0x140]
                    print(f"  --- 引用者 {ref_va:#x} ---")
                    for insn in md.disasm(code, start):
                        mark = " <<<" if insn.address == ref_va else ""
                        print(f"  {insn.address:#010x}: {insn.mnemonic:<8} {insn.op_str}{mark}")
                        if insn.address >= ref_va + 0x60:
                            break
                    break


if __name__ == "__main__":
    main()
