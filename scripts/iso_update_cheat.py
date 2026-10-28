#!/usr/bin/env python3
"""
iso_update_cheat.py — 将魔改组件整合打包入 PSUA ISO

步骤：
1. 更新 /ERX/PSU.GZ;1 (写入 extent 916 并更新 /ERX 目录记录)
2. 更新 PSUROFS.CVM;1 (写入 extent 344925，后随文件顺移)
3. 更新 SLPM_666.63;1 (写入其 extent)
4. 更新根目录记录、ERX 目录记录与 PVD 卷大小（全部支持 LE 与 BE 双端）
"""

import os
import struct
import sys

CVM_NAME = b"PSUROFS.CVM;1"
SLPM_NAME = b"SLPM_666.63;1"
PSU_GZ_NAME = b"PSU.GZ;1"
SEC = 2048

def parse_dir_records(f, root_extent, root_size):
    recs = []
    for s in range(root_extent, root_extent + (root_size + SEC - 1) // SEC):
        f.seek(s * SEC)
        buf = f.read(SEC)
        pos = 0
        while pos < SEC:
            rec_len = buf[pos]
            if rec_len == 0:
                break
            name_len = buf[pos + 32]
            flags = buf[pos + 25]
            extent = struct.unpack_from("<I", buf, pos + 2)[0]
            size = struct.unpack_from("<I", buf, pos + 10)[0]
            name = bytes(buf[pos + 33:pos + 33 + name_len])
            if not (name_len == 1 and buf[pos + 33] in (0, 1)):
                recs.append((name, s * SEC + pos, rec_len, extent, size, flags))
            pos += rec_len
    return recs

def build_cheat_iso(src_iso, new_cvm, new_slpm, new_psu_gz, out_iso):
    print(f"[*] Reading source ISO: {src_iso}")
    f = open(src_iso, "rb")
    f.seek(16 * SEC)
    pvd = f.read(SEC)
    assert pvd[:8] == b"\x01CD001\x01\x00", "不是标准 ISO9660"

    root_extent = struct.unpack_from("<I", pvd, 158)[0]
    root_size = struct.unpack_from("<I", pvd, 166)[0]
    recs = parse_dir_records(f, root_extent, root_size)
    by_name = {r[0]: r for r in recs}

    # 1. CVM 信息
    name, cvm_recoff, _, cvm_extent, cvm_size, _ = by_name[CVM_NAME]
    new_cvm_size = os.path.getsize(new_cvm)
    assert new_cvm_size % SEC == 0, "CVM 必须扇区对齐"

    movers = [r for r in recs if r[3] > cvm_extent and r[0] != CVM_NAME]
    old_secs = (cvm_size + SEC - 1) // SEC
    new_secs = new_cvm_size // SEC
    delta = new_secs - old_secs
    print(f"[*] CVM: {cvm_size}B -> {new_cvm_size}B (delta={delta} sectors), 顺移文件: {[m[0].decode() for m in movers]}")

    # 2. 读取新的可执行组件
    slpm_data = open(new_slpm, "rb").read()
    psu_gz_data = open(new_psu_gz, "rb").read()
    print(f"[*] SLPM_666.63: {len(slpm_data)} bytes, PSU.GZ: {len(psu_gz_data)} bytes")

    out = open(out_iso, "wb")

    # 阶段 1: 写入 CVM 之前的所有扇区 (0 .. cvm_extent * SEC)
    # 注意: /ERX/PSU.GZ;1 位于 extent 916，在 CVM 之前！我们需要在此段中替换 PSU.GZ
    print(f"[*] Writing pre-CVM sectors (0 .. {cvm_extent})...")
    psu_gz_extent = 916
    psu_gz_alloc_secs = (len(psu_gz_data) + SEC - 1) // SEC

    # 写入 0 到 extent 916 之前
    f.seek(0)
    out.write(f.read(psu_gz_extent * SEC))

    # 写入新的 PSU_cheat.GZ 并填充扇区对齐
    out.write(psu_gz_data)
    pad_psu = (psu_gz_alloc_secs * SEC) - len(psu_gz_data)
    if pad_psu > 0:
        out.write(b"\0" * pad_psu)

    # 跳过原 ISO 中 PSU.GZ 占用的空间，写入到 cvm_extent 之前
    # 原 PSU.GZ 占用从 extent 916 开始
    orig_psu_gz_secs = (2894514 + SEC - 1) // SEC
    cur_pos = (psu_gz_extent + psu_gz_alloc_secs) * SEC
    f.seek((psu_gz_extent + orig_psu_gz_secs) * SEC)

    # 填补由于新 PSU.GZ 较小产生的扇区空隙（保证后续文件 extent 稳定）
    sec_gap = orig_psu_gz_secs - psu_gz_alloc_secs
    if sec_gap > 0:
        out.write(b"\0" * (sec_gap * SEC))

    # 继续从原 ISO 复制直到 CVM 起始 extent
    f.seek((psu_gz_extent + orig_psu_gz_secs) * SEC)
    remain = (cvm_extent - (psu_gz_extent + orig_psu_gz_secs)) * SEC
    while remain > 0:
        chunk = f.read(min(1 << 22, remain))
        out.write(chunk)
        remain -= len(chunk)

    # 阶段 2: 写入新 CVM
    print(f"[*] Writing new PSUROFS.CVM ({new_cvm_size} bytes)...")
    with open(new_cvm, "rb") as nc:
        while True:
            chunk = nc.read(1 << 22)
            if not chunk:
                break
            out.write(chunk)

    # 阶段 3: 写入 CVM 之后的文件（按顺移新位置写入）
    # 其中包含 SLPM_666.63;1，需要写入魔改后的 slpm_data
    print("[*] Writing post-CVM files...")
    pos = out.tell()
    for r in sorted(movers, key=lambda r: r[3]):
        r_name, _, _, extent, size, _ = r
        new_ext = extent + delta
        target = new_ext * SEC
        if pos < target:
            out.write(b"\0" * (target - pos))
            pos = target

        if r_name == SLPM_NAME:
            print(f"  [+] Injecting patched SLPM_666.63 at sector {new_ext}...")
            out.write(slpm_data)
            pad_slpm = ((-len(slpm_data)) % SEC)
            if pad_slpm > 0:
                out.write(b"\0" * pad_slpm)
            pos += len(slpm_data) + pad_slpm
        else:
            f.seek(extent * SEC)
            remain = size
            while remain > 0:
                chunk = f.read(min(1 << 22, remain))
                out.write(chunk)
                remain -= len(chunk)
                pos += len(chunk)

    tail_align = (-pos) % SEC
    if tail_align > 0:
        out.write(b"\0" * tail_align)
    total_iso_size = out.tell()
    out.close()
    f.close()

    # 阶段 4: 原地补丁目录记录与 PVD (双端 LE/BE 兼容)
    print("[*] Patching ISO directory records and PVD...")
    out = open(out_iso, "r+b")

    def patch_word(offset, val):
        out.seek(offset)
        out.write(struct.pack("<I", val))
        out.write(struct.pack(">I", val))

    # 更新 CVM 记录的大小
    out.seek(cvm_recoff + 10)
    out.write(struct.pack("<I", new_cvm_size))
    out.write(struct.pack(">I", new_cvm_size))

    # 更新 CVM 后顺移文件的 extent
    for r in movers:
        out.seek(r[1] + 2)
        out.write(struct.pack("<I", r[3] + delta))
        out.write(struct.pack(">I", r[3] + delta))

    # 更新 /ERX 目录中 PSU.GZ;1 的文件大小
    # ERX 目录位于扇区 262，PSU.GZ 记录位于偏移 394 (0x18A)
    erx_psu_recoff = 262 * SEC + 394
    out.seek(erx_psu_recoff + 10)
    out.write(struct.pack("<I", len(psu_gz_data)))
    out.write(struct.pack(">I", len(psu_gz_data)))

    # 更新 PVD 扇区总数
    out.seek(16 * SEC + 80)
    out.write(struct.pack("<I", total_iso_size // SEC))
    out.write(struct.pack(">I", total_iso_size // SEC))

    out.close()
    print(f"[+] 成功构建魔改 ISO: {out_iso} ({total_iso_size} 字节, {total_iso_size/2**30:.2f} GB)")

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else 'work/original/PSUA.iso'
    cvm = sys.argv[2] if len(sys.argv) > 2 else 'work/PSUROFS_cn_build.cvm'
    slpm = sys.argv[3] if len(sys.argv) > 3 else 'work/elf/SLPM_666.63_cheat'
    psu_gz = sys.argv[4] if len(sys.argv) > 4 else 'work/elf/PSU_cheat.GZ'
    out = sys.argv[5] if len(sys.argv) > 5 else 'work/PSUA_cheat_build.iso'

    build_cheat_iso(src, cvm, slpm, psu_gz, out)
