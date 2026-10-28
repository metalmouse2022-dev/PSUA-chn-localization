#!/usr/bin/env python3
"""trans_fill.py — 把批量译文填进翻译 txt 的 < 行（只改 < 行，其他行原样保留）。

批量文件格式（TSV，UTF-8）：每行 `编号<TAB>译文`，空行与 # 开头注释行忽略。
用法: python trans_fill.py <batch.tsv> [目标txt ...]   （缺省=work/translation/词条库_*.txt）
译文为空串时跳过该条（不填）。
"""
import glob
import os
import re
import sys

U_ESC = re.compile(r"\\u([0-9a-fA-F]{4})")


def unescape_u(text):
    """批量文件里的 \\uXXXX 转成真实字符（用于保留 PUA 图标/玩家名占位符）"""
    return U_ESC.sub(lambda m: chr(int(m.group(1), 16)), text)


def load_batch(path):
    trans = {}
    for ln, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        seq, sep, text = line.partition("\t")
        if not sep:
            print(f"[批量文件错误] 第{ln}行缺少 TAB: {line[:60]!r}")
            sys.exit(1)
        seq = seq.strip()
        if seq in trans:
            print(f"[批量文件错误] 重复编号 {seq}")
            sys.exit(1)
        if text:
            trans[seq] = unescape_u(text)
    return trans


def main():
    batch_path = sys.argv[1]
    if len(sys.argv) > 2:
        targets = sys.argv[2:]
    else:
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "work", "translation")
        targets = sorted(glob.glob(os.path.join(root, "词条库_*.txt")))
    trans = load_batch(batch_path)
    if not trans:
        print("批量文件无有效译文")
        sys.exit(1)
    remaining = dict(trans)
    n_filled = 0
    for path in targets:
        with open(path, encoding="utf-8", newline="") as f:
            lines = f.read().split("\n")
        cur_seq = None
        changed = False
        for i, ln in enumerate(lines):
            if ln.startswith("# ") and len(ln) > 2 and ln[2:].split(" ", 1)[0].isdigit():
                cur_seq = ln[2:].split(" ", 1)[0]
            elif ln.startswith("<") and cur_seq in remaining:
                lines[i] = "< " + remaining[cur_seq]
                del remaining[cur_seq]
                n_filled += 1
                changed = True
        if changed:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write("\n".join(lines))
    print(f"已填 {n_filled} 条")
    if remaining:
        for seq in list(remaining)[:20]:
            print(f"  [未命中] {seq}")
        print(f"结果: {len(remaining)} 条编号未找到")
        sys.exit(1)
    print("结果: 全部命中")


if __name__ == "__main__":
    main()
