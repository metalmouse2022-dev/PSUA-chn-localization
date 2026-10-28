#!/usr/bin/env python3
r"""trans_check_chars.py — 预检批量TSV译文里的字库外字符（回填前用）。
用法: python trans_check_chars.py <batch.tsv>
输出: 每条含 GB2312一级字库外/原字库外 字符的 编号+字符。PUA及其后1字符视为控制码放行。
"""
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
U_ESC = re.compile(r"\\u([0-9a-fA-F]{4})")
ALLOWED_PUNCT = set("，。！？、：；「」『』（）…—・～‘’“”％℃°±×÷＝≠＜＞　")


def load_allowed():
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
    for hi in range(0xB0, 0xD8):
        for lo in range(0xA1, 0xFF):
            try:
                allowed.add(bytes([hi, lo]).decode("gb2312"))
            except Exception:
                pass
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sega = open(os.path.join(root, "work", "nbl_out", "DE_FONT", "sega.bin"), "rb").read()
    for i in range(len(sega) // 3):
        allowed.add(chr((sega[i * 3] << 8) | sega[i * 3 + 1]))
    allowed |= ALLOWED_PUNCT
    return allowed


def main():
    allowed = load_allowed()
    bad_total = 0
    for ln in open(sys.argv[1], encoding="utf-8"):
        ln = ln.rstrip("\r\n")
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        seq, _, text = ln.partition("\t")
        text = U_ESC.sub(lambda m: chr(int(m.group(1), 16)), text)
        prev_pua = False
        bad = []
        for c in text:
            if 0xE000 <= ord(c) <= 0xF8FF:
                prev_pua = True
                continue
            if prev_pua:
                prev_pua = False
                continue
            if c not in allowed and c not in "\n\r\t":
                bad.append(c)
        if bad:
            bad_total += 1
            print(seq, "".join(bad))
    if bad_total:
        print(f"共 {bad_total} 条含字库外字符")
    else:
        print("OK 全部用字在字库内")


if __name__ == "__main__":
    main()
