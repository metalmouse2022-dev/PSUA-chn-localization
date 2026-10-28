#!/usr/bin/env python3
"""afs.py — CRI AFS / MiniAFS 容器解析与重建。

标准 AFS:  "AFS\\0" + u32 条目数 + (n+1) 个 u32 偏移(单调, n起始+1结束)
MiniAFS:   "AFS\\0" + u32 (条目数-1) + (count+1) 对 (起始u32, 大小u32)
           ← count 字段是"最后一个条目的索引"，实际对数 = count+1！
条目数据 0x800 对齐；尾部可能有文件名区（保留原样）。
"""
import struct


def parse(data: bytes):
    """返回 (entries[(start,size)], is_pair, tail_offset)"""
    assert data[:4] == b"AFS\x00"
    n = struct.unpack_from("<I", data, 4)[0]
    if n <= 0 or n > 8192:
        raise ValueError(f"AFS 条目数异常: {n}")
    # 标准 AFS: 单调偏移 (n 个起始 + 1 结束)
    if n + 1 <= 8192:
        vals = struct.unpack_from(f"<{n + 1}I", data, 8)
        if all(vals[i] <= vals[i + 1] for i in range(n)) and vals[0] >= 0x800 \
                and vals[n] <= len(data):
            entries = [(vals[i], vals[i + 1] - vals[i]) for i in range(n)]
            return entries, False, vals[n]
    # MiniAFS: count+1 对 (起始,大小)
    n_pairs = n + 1
    pairs = struct.unpack_from(f"<{2 * n_pairs}I", data, 8)
    ok = all(pairs[2 * k] >= 0x800 and pairs[2 * k + 1] > 0
             and pairs[2 * k] + pairs[2 * k + 1] <= len(data)
             for k in range(n_pairs))
    if ok:
        entries = [(pairs[2 * k], pairs[2 * k + 1]) for k in range(n_pairs)]
        raw_end = max(s + z for s, z in entries)
        end = (raw_end + 0x7FF) // 0x800 * 0x800  # 尾部从条目区对齐末尾起
        return entries, True, end
    raise ValueError("无法识别的 AFS 变体")


def pack(entry_blobs, pair_mode: bool, tail: bytes = b"", align=0x800, header_reserve=0x800):
    """重建 AFS。entry_blobs: [bytes]。保持原模式与尾部。
    header_reserve: 头部保留区大小（原版为 0x800；对数多时自动扩展）。"""
    if pair_mode:
        nvals = len(entry_blobs) * 2
        header_size = 8 + 4 * nvals
        first = max(header_size, header_reserve)
        first = (first + align - 1) // align * align
        starts, sizes = [], []
        pos = first
        for b in entry_blobs:
            starts.append(pos)
            sizes.append(len(b))
            pos = (pos + len(b) + align - 1) // align * align
        out = bytearray()
        out += b"AFS\x00" + struct.pack("<I", len(entry_blobs) - 1)  # count = 条目数-1
        for s, z in zip(starts, sizes):
            out += struct.pack("<II", s, z)
        out += b"\0" * (first - len(out))
        for b in entry_blobs:
            out += b
            out += b"\0" * ((-len(b)) % align)
        out += tail
        return bytes(out)
    else:
        header_size = 8 + 4 * (len(entry_blobs) + 1)
        first = max(header_size, header_reserve)
        first = (first + align - 1) // align * align
        starts = []
        pos = first
        for b in entry_blobs:
            starts.append(pos)
            pos = (pos + len(b) + align - 1) // align * align
        out = bytearray()
        out += b"AFS\x00" + struct.pack("<I", len(entry_blobs))
        for s in starts:
            out += struct.pack("<I", s)
        out += struct.pack("<I", pos)
        out += b"\0" * (first - len(out))
        for b in entry_blobs:
            out += b
            out += b"\0" * ((-len(b)) % align)
        out += tail
        return bytes(out)
