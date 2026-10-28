#!/usr/bin/env python3
"""text_tool.py — PSU 文本文件（*Text*.bin 等）全量导出/回写工具。

文件结构（已逆向）:
  u32@0  总大小
  u32@4  恒为 8（指向 @8 的"表指针"字段位置）
  u32@8  字符串偏移表起始 T
  [12, T) 分组边界描述符 u32 数组（文件绝对偏移, 指向表内条目位置; 无分组时 T=12）
  [T, 数据区) 字符串偏移表（u32 × N, 升序指向字符串）
  数据区   NUL 终止 UTF-16LE 字符串紧密排列（偶对齐）
  尾部     可能有 padding/附加数据（原样保留）

用法:
  python text_tool.py export <目录> <输出.json>      # 导出全部字符串
  python text_tool.py import <原目录> <翻译.json> <输出目录>   # 回写
"""
import json
import os
import struct
import sys


def read_str16(d: bytes, v: int) -> str:
    """读 NUL 终止 UTF-16LE 串。按 2 字节步进找终止符；
    起始偏移可能为奇数（事件文本变体），字节切片处理。"""
    i = v
    while i + 1 < len(d):
        if d[i] == 0 and d[i + 1] == 0:
            return d[v:i].decode("utf-16-le", "replace")
        i += 2
    return d[v:].decode("utf-16-le", "replace")


def str_end(d: bytes, v: int) -> int:
    """串末尾（含终止符）的偏移"""
    i = v
    while i + 1 < len(d):
        if d[i] == 0 and d[i + 1] == 0:
            return i + 2
        i += 2
    return len(d)


def parse(d: bytes):
    size, p1, T = struct.unpack_from("<III", d, 0)
    assert p1 == 8, f"异常头部 @4={p1}"
    descs = []
    off = 12
    while off < T:
        descs.append(struct.unpack_from("<I", d, off)[0])
        off += 4
    tbl = []
    off = T
    while off + 4 <= size:
        v = struct.unpack_from("<I", d, off)[0]
        if v < off + 4 or v >= size:  # 表结束
            break
        tbl.append(v)
        off += 4
    strs = [read_str16(d, v) for v in tbl]
    tail_start = str_end(d, tbl[-1]) if tbl else size
    tail = d[tail_start:]
    return {"size": size, "T": T, "descs": descs, "tbl": tbl,
            "strs": strs, "tail": tail, "data_start": tbl[0] if tbl else size, "raw": d}


def build(parsed, new_strs):
    """重建二进制：保持字符串数与分组语义，允许变长。"""
    n = len(parsed["strs"])
    assert len(new_strs) == n, f"字符串数不符 {len(new_strs)} != {n}"
    # 新偏移计算: 头12 + 描述符 + 表 + 字符串
    n_desc = len(parsed["descs"])
    new_T = 12 + 4 * n_desc
    encs = [s.encode("utf-16-le") + b"\x00\x00" for s in new_strs]
    offsets = []
    pos = new_T + 4 * n
    for e in encs:
        offsets.append(pos)
        pos += len(e)
    total = pos + len(parsed["tail"])
    out = bytearray()
    out += struct.pack("<III", total, 8, new_T)
    # 描述符: 保持"表内条目位置"语义 → 新位置 = 新T + (旧值 - 旧T)
    for dv in parsed["descs"]:
        out += struct.pack("<I", new_T + (dv - parsed["T"]))
    for o in offsets:
        out += struct.pack("<I", o)
    for e in encs:
        out += e
    out += parsed["tail"]
    assert len(out) == total
    return bytes(out)


def export_dir(src_dir, out_json):
    result = {}
    for dirpath, _, files in os.walk(src_dir):
        for fn in sorted(files):
            if not fn.endswith(".bin"):
                continue
            p = os.path.join(dirpath, fn)
            d = open(p, "rb").read()
            try:
                parsed = parse(d)
            except Exception as e:
                print(f"跳过 {fn}: {e}")
                continue
            rel = os.path.relpath(p, src_dir).replace("\\", "/")
            result[rel] = parsed["strs"]
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    total = sum(len(v) for v in result.values())
    print(f"导出 {len(result)} 个文件, {total} 条字符串 -> {out_json}")


def import_dir(src_dir, trans_json, out_dir):
    trans = json.load(open(trans_json, encoding="utf-8"))
    n_files = n_strs = 0
    for dirpath, _, files in os.walk(src_dir):
        for fn in sorted(files):
            if not fn.endswith(".bin"):
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, src_dir).replace("\\", "/")
            if rel not in trans:
                continue
            d = open(p, "rb").read()
            try:
                parsed = parse(d)
            except Exception:
                continue
            new_strs = [t["cn"] if isinstance(t, dict) and t.get("cn") else
                        (t if isinstance(t, str) else s)
                        for t, s in zip(trans[rel], parsed["strs"])]
            out = build(parsed, new_strs)
            dst = os.path.join(out_dir, rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            open(dst, "wb").write(out)
            n_files += 1
            n_strs += len(new_strs)
    print(f"回写 {n_files} 个文件, {n_strs} 条字符串 -> {out_dir}")


def roundtrip_test(src_dir):
    """导出->回写(不变) 应产生可解析且字符串一致的结果"""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        jp = os.path.join(td, "a.json")
        od = os.path.join(td, "out")
        export_dir(src_dir, jp)
        import_dir(src_dir, jp, od)
        bad = 0
        for dirpath, _, files in os.walk(src_dir):
            for fn in files:
                if not fn.endswith(".bin"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), src_dir)
                a = open(os.path.join(dirpath, fn), "rb").read()
                bp = os.path.join(od, rel)
                if not os.path.isfile(bp):
                    continue
                b = open(bp, "rb").read()
                pa, pb = parse(a), parse(b)
                if pa["strs"] != pb["strs"] or pa["descs"] != pb["descs"]:
                    bad += 1
                    print(f"不一致: {rel}")
                elif a != b:
                    print(f"字节不同但结构一致: {rel} ({len(a)} -> {len(b)})")
        print("回环测试:", "全部一致" if bad == 0 else f"{bad} 个文件异常")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "export":
        export_dir(sys.argv[2], sys.argv[3])
    elif cmd == "import":
        import_dir(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "roundtrip":
        roundtrip_test(sys.argv[2])
