#!/usr/bin/env python3
"""find_mount_calls.py — 在 PSU_ERX.elf 中定位加载指定字符串地址的代码，
反汇编上下文，追踪 ROFS 挂载调用与密码参数。

用法: python find_mount_calls.py <elf> <文件内字符串偏移> [窗口大小]
"""
import sys
from capstone import Cs, CS_ARCH_MIPS, CS_MODE_MIPS64
from elftools.elf.elffile import ELFFile


def main():
    elf_path = sys.argv[1]
    str_off = int(sys.argv[2], 0)
    window = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0x200

    f = open(elf_path, "rb")
    elf = ELFFile(f)

    # 文件偏移 -> 虚拟地址 映射（PT_LOAD 段）
    loads = []
    for seg in elf.iter_segments():
        if seg.header.p_type == "PT_LOAD":
            loads.append((seg.header.p_offset, seg.header.p_filesz,
                          seg.header.p_vaddr, seg.header.p_memsz))
    print("PT_LOAD 段:", [(hex(o), hex(s), hex(v)) for o, s, v, m in loads])

    def off2va(off):
        for o, s, v, m in loads:
            if o <= off < o + s:
                return v + (off - o)
        return None

    va = off2va(str_off)
    print(f"字符串文件偏移 {str_off:#x} -> VA {va:#x}")
    if va is None:
        return

    # MIPS 加载地址模式: lui $rX, hi; ori/addiu $rX, $rX, lo
    hi = (va + 0x8000) >> 16
    lo = va & 0xFFFF
    lo_signed = lo - 0x10000 if lo >= 0x8000 else lo
    print(f"地址常数: lui={hi:#x} ori_lo={lo:#x} addiu_lo={lo_signed}")

    # 扫描全部可执行段找引用
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS64)
    md.detail = True
    data = open(elf_path, "rb").read()

    refs = []
    for o, s, v, m in loads:
        seg = data[o:o + s]
        # 按半字扫描 ori 立即数 lo（粗筛）
        import struct as st
        words = st.unpack(f">{s//4}I", seg[: s // 4 * 4])
        for i, w in enumerate(words):
            op = w >> 26
            imm = w & 0xFFFF
            # ori(0xD) addiu(0x9) lw/sw 基址偏移都可能是 lo
            if imm == lo:
                refs.append((v + i * 4, "imm"))
    print(f"lo 引用点: {len(refs)}")
    for rva, kind in refs[:20]:
        print(f"  VA {rva:#x}")
        # 反汇编窗口
        for o, s, v, m in loads:
            if v <= rva < v + s:
                start = max(v, rva - window)
                off = o + (start - v)
                code = data[off:off + window * 2]
                for insn in md.disasm(code, start):
                    mark = " <<<" if insn.address == rva else ""
                    print(f"  {insn.address:#010x}: {insn.mnemonic:<10} {insn.op_str}{mark}")
                    if insn.address > rva + 0x40:
                        break
                break
        print()


if __name__ == "__main__":
    main()
