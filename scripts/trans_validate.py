#!/usr/bin/env python3
"""trans_validate.py — 校验翻译 txt（回填前必须通过）。

块格式: # 序号 [上下文] @容器:索引 / > 原文 / < 译文 / 空行
检查: 结构、转义、格式符(%s等)、字库字符集、条目覆盖完整性、译文假名残留提醒。
用法: python trans_validate.py <translation目录>
退出码 0=通过(可有提醒) 1=有错误
"""
import glob
import json
import os
import re
import sys

FORMAT_RE = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?[sdfecxX%]")
ALLOWED_PUNCT = set("，。！？、：；「」『』（）…—・～‘’“”％℃°±×÷＝≠＜＞　")

_ALLOWED_CACHE = None


def load_allowed():
    global _ALLOWED_CACHE
    if _ALLOWED_CACHE is None:
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")
        # GB2312 一级
        for hi in range(0xB0, 0xD8):
            for lo in range(0xA1, 0xFF):
                try:
                    allowed.add(bytes([hi, lo]).decode("gb2312"))
                except Exception:
                    pass
        # 原字库已有字
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sega = open(os.path.join(root, "work", "nbl_out", "DE_FONT", "sega.bin"), "rb").read()
        for i in range(len(sega) // 3):
            allowed.add(chr((sega[i * 3] << 8) | sega[i * 3 + 1]))
        allowed |= ALLOWED_PUNCT
        _ALLOWED_CACHE = allowed
    return _ALLOWED_CACHE


def unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            if i + 1 >= len(s):
                raise ValueError("行尾孤立反斜杠")
            n = s[i + 1]
            if n == "n":
                out.append("\n")
            elif n == "r":
                out.append("\r")
            elif n == "t":
                out.append("\t")
            elif n == "\\":
                out.append("\\")
            else:
                raise ValueError(f"未知转义 \\{n}")
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


def parse_blocks(path):
    """返回 [(seq, container, idx, jp_esc, cn_esc)] 与结构错误"""
    lines = open(path, encoding="utf-8").read().split("\n")
    blocks = []
    errors = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln.strip() or ln.startswith("【"):
            i += 1
            continue
        m = re.match(r"^# (\d{5,}) \[[^\]]*\] @(.+):(\d+)$", ln)
        if not m:
            errors.append(f"{os.path.basename(path)} 行{i+1}: # 行格式错误: {ln[:50]!r}")
            i += 1
            continue
        seq, container, idx = int(m.group(1)), m.group(2), int(m.group(3))
        if i + 2 >= len(lines):
            errors.append(f"{os.path.basename(path)} #{seq}: 块不完整")
            break
        jp = lines[i + 1]
        # 可选 = 官方繁中参考行
        if jp.startswith("> ") and i + 3 < len(lines) and \
                lines[i + 2].startswith("= ") and lines[i + 3].startswith("< "):
            blocks.append((seq, container, idx, jp[2:], lines[i + 3][2:]))
            i += 4
            continue
        cn = lines[i + 2]
        if not jp.startswith("> ") or not cn.startswith("< "):
            errors.append(f"{os.path.basename(path)} #{seq}: >/< 行缺失或被改动")
            i += 1
            continue
        blocks.append((seq, container, idx, jp[2:], cn[2:]))
        i += 3
    return blocks, errors


def main():
    root = sys.argv[1]
    manifest = json.load(open(os.path.join(root, "manifest.json"), encoding="utf-8"))
    allowed = load_allowed()
    known_containers = {c for lst in manifest.values() for c in lst} | {"GLOSSARY"}
    all_errors, all_warns = [], []
    n_total = n_translated = 0
    # (container, idx) 去重检查
    seen = {}

    for txt in sorted(glob.glob(os.path.join(root, "*.txt"))):
        base = os.path.basename(txt)
        if base not in manifest:
            all_errors.append(f"{base}: 不在 manifest（勿新建文件）")
            continue
        blocks, errors = parse_blocks(txt)
        all_errors += errors
        for seq, container, idx, jp_esc, cn_esc in blocks:
            n_total += 1
            if container not in known_containers:
                all_errors.append(f"{base} #{seq}: 未知容器 {container}")
                continue
            key = (container, idx)
            if key in seen:
                all_errors.append(f"{base} #{seq}: 重复条目 {container}:{idx}")
            seen[key] = True
            try:
                unescape(jp_esc)
            except ValueError as e:
                all_errors.append(f"{base} #{seq}: 原文转义异常({e})——原文被改动?")
                continue
            if not cn_esc.strip():
                continue
            n_translated += 1
            try:
                cn = unescape(cn_esc)
            except ValueError as e:
                all_errors.append(f"{base} #{seq}: {e}")
                continue
            fj = [x for x in FORMAT_RE.findall(jp_esc) if x != "%%"]
            fc = [x for x in FORMAT_RE.findall(cn_esc) if x != "%%"]
            if fj != fc:
                all_errors.append(f"{base} #{seq} {container}:{idx}: 格式符不一致 原文{fj} 译文{fc}")
            bad = set()
            prev_pua = False
            for c in cn:  # PUA及其后1字符=游戏控制码(玩家名/音效/动作指令),不参与渲染
                if 0xE000 <= ord(c) <= 0xF8FF:
                    prev_pua = True
                    continue
                if prev_pua:
                    prev_pua = False
                    continue
                if c not in allowed and c not in "\n\r\t":
                    bad.add(c)
            if bad:
                all_errors.append(f"{base} #{seq}: 字库外字符 {''.join(sorted(bad))[:20]}")
            if jp_esc == cn_esc and re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", cn):
                all_warns.append(f"{base} #{seq}: 译文=原文(未翻?)")
            if "台词" not in container and "QE" not in container and len(cn) > 28:
                all_warns.append(f"{base} #{seq}: 译文较长({len(cn)}字)")

    print(f"共 {n_total} 条, 已译 {n_translated} 条")
    for e in all_errors[:50]:
        print("  [错误]", e)
    if len(all_errors) > 50:
        print(f"  ... 共 {len(all_errors)} 个错误")
    for w in all_warns[:15]:
        print("  [提醒]", w)
    if len(all_warns) > 15:
        print(f"  ... 共 {len(all_warns)} 个提醒")
    if all_errors:
        print(f"结果: 未通过（{len(all_errors)} 错误）")
        sys.exit(1)
    print(f"结果: 通过（{len(all_warns)} 提醒）")


if __name__ == "__main__":
    main()
