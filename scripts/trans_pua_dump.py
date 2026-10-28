#!/usr/bin/env python3
r"""trans_pua_dump.py — 导出翻译txt中含PUA(私有区)字符条目的转义形式。
用法: python trans_pua_dump.py <txt> [起始编号]
输出: `# 编号` + 转义后的原文行（反斜杠uXXXX形式），供翻译时原样保留控制码。
"""
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BS = chr(92)


def main():
    path = sys.argv[1]
    start = int(sys.argv[2]) if len(sys.argv) > 2 else -1
    seq = None
    for ln in open(path, encoding="utf-8"):
        ln = ln.rstrip("\n")
        if ln.startswith("# "):
            seq = int(ln.split(" ")[1])
        elif ln.startswith("> ") and seq >= start:
            if any(0xE000 <= ord(c) <= 0xF8FF for c in ln):
                s = "".join((BS + "u%04X" % ord(c)) if ord(c) >= 0xE000 else c
                            for c in ln[2:])
                print(seq, s)


if __name__ == "__main__":
    main()
