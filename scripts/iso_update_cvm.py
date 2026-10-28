#!/usr/bin/env python3
"""iso_update_cvm.py — 更新 PSUA.iso 中的 PSUROFS.CVM（流式，大小可变）。

流程: 新 CVM 写回原 extent，其后文件顺移；目录记录/PVD 原地补丁。
用法: python iso_update_cvm.py <原.iso> <新.cvm> <输出.iso>
"""
import struct
import sys

CVM_NAME = b"PSUROFS.CVM;1"
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


def main(src_iso, new_cvm, out_iso):
    f = open(src_iso, "rb")
    f.seek(16 * SEC)
    pvd = f.read(SEC)
    assert pvd[:8] == b"\x01CD001\x01\x00", "不是 ISO9660"
    vol_secs = struct.unpack_from("<I", pvd, 80)[0]
    root_extent = struct.unpack_from("<I", pvd, 158)[0]
    root_size = struct.unpack_from("<I", pvd, 166)[0]
    recs = parse_dir_records(f, root_extent, root_size)
    by_name = {r[0]: r for r in recs}

    name, cvm_recoff, _, cvm_extent, cvm_size, _ = by_name[CVM_NAME]
    new_data_size = __import__("os").path.getsize(new_cvm)
    assert new_data_size % SEC == 0, "CVM 必须扇区对齐"

    movers = [r for r in recs if r[3] > cvm_extent and r[0] != CVM_NAME]
    old_secs = (cvm_size + SEC - 1) // SEC
    new_secs = new_data_size // SEC
    delta = new_secs - old_secs
    print(f"CVM: {cvm_size}B -> {new_data_size}B (Δ={delta}扇区), 需移动 {len(movers)} 文件: {[m[0].decode() for m in movers]}")

    out = open(out_iso, "wb")
    # 1) CVM 之前原样
    f.seek(0)
    remain = cvm_extent * SEC
    while remain:
        chunk = f.read(min(1 << 22, remain))
        out.write(chunk)
        remain -= len(chunk)
    # 2) 新 CVM
    with open(new_cvm, "rb") as nc:
        while True:
            chunk = nc.read(1 << 22)
            if not chunk:
                break
            out.write(chunk)
    # 3) 移动的文件（按 extent 顺序，逐个从源复制到新位置）
    pos = out.tell()
    for r in sorted(movers, key=lambda r: r[3]):
        _, _, _, extent, size, _ = r
        new_ext = extent + delta
        target = new_ext * SEC
        if pos < target:
            out.write(b"\0" * (target - pos))
            pos = target
        f.seek(extent * SEC)
        remain = size
        while remain:
            chunk = f.read(min(1 << 22, remain))
            out.write(chunk)
            remain -= len(chunk)
            pos += len(chunk)
    tail_align = (-pos) % SEC
    out.write(b"\0" * tail_align)
    total = out.tell()
    out.close()
    f.close()

    # 4) 原地补丁: 目录记录 + PVD
    out = open(out_iso, "r+b")

    def patch(off, fmt, val):
        out.seek(off)
        out.write(struct.pack(fmt, val))

    patch(cvm_recoff + 10, "<I", new_data_size)
    patch(cvm_recoff + 14, ">I", new_data_size)
    for r in movers:
        patch(r[1] + 2, "<I", r[3] + delta)
        patch(r[1] + 6, ">I", r[3] + delta)
    patch(16 * SEC + 80, "<I", total // SEC)
    patch(16 * SEC + 84, ">I", total // SEC)
    out.close()
    print(f"[完成] {out_iso} = {total} B ({total/2**30:.2f} GB, {total//SEC} 扇区)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
