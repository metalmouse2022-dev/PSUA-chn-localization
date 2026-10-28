#!/usr/bin/env python3
"""scan_sjis.py — 扫描目录下所有文件中的 Shift-JIS 文本密度，输出排行。

用法: python scan_sjis.py <目录> [输出.tsv] [--min-ratio 0.02]
判定: 双字节 SJIS（含汉字/假名）连续片段 >= 4 字符算有效文本串。
"""
import os
import re
import sys

# SJIS 双字节: 第一字节 0x81-0x9F / 0xE0-0xEF，第二字节 0x40-0x7E / 0x80-0xFC
# 其中汉字/假名区: 第一字节 0x82(平假名)/0x83(片假名)/0x88-0x9F,0xE0-0xEA(汉字)
DB = rb'(?:[\x82\x83]|[\x88-\x9f\xe0-\xea][\x40-\x7e\x80-\xfc]|[\x82\x83][\x40-\x7e\x80-\xfc])'
RUN = re.compile(rb'(?:[\x81-\x9f\xe0-\xef][\x40-\x7e\x80-\xfc]){4,}')


def has_kana_kanji(s: bytes) -> bool:
    return any(c in (0x82, 0x83) or 0x88 <= c <= 0x9F or 0xE0 <= c <= 0xEA for c in s[::2])


def main():
    root = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else None
    rows = []
    for dirpath, _, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            try:
                d = open(p, "rb").read()
            except OSError:
                continue
            if not d:
                continue
            hits = [m.group() for m in RUN.finditer(d)]
            hits = [h for h in hits if has_kana_kanji(h)]
            if not hits:
                continue
            nbytes = sum(len(h) for h in hits)
            ratio = nbytes / len(d)
            sample = b" | ".join(hits[:3])[:60]
            rows.append((ratio, nbytes, len(hits), os.path.relpath(p, root), sample))
    rows.sort(reverse=True)
    print(f"{'占比':>6} {'字节':>9} {'串数':>6}  文件 / 样例")
    for ratio, nb, n, rel, sample in rows[:50]:
        try:
            txt = sample.decode("shift-jis", "replace")
        except Exception:
            txt = "?"
        print(f"{ratio:>6.1%} {nb:>9} {n:>6}  {rel}  {txt[:40]}")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            for ratio, nb, n, rel, sample in rows:
                try:
                    txt = sample.decode("shift-jis", "replace").replace("\t", " ")
                except Exception:
                    txt = ""
                f.write(f"{ratio:.4f}\t{nb}\t{n}\t{rel}\t{txt}\n")
        print("已写入", out_path, "共", len(rows), "个含文本文件")


if __name__ == "__main__":
    main()
