#!/usr/bin/env python3
"""不依赖游戏资源的最小检查：语法、PRS、AFS/MiniAFS 和 UTF-16 文本。

用法：python -B scripts/smoke_check.py
所有二进制样例在内存中构造；不读取游戏输入、不产生构建产物。
这些检查不代表完整汉化构建、模拟器或实机验证通过。
"""
import random
import struct
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import afs
import prs
import text_tool


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def check_syntax():
    paths = sorted(Path(__file__).resolve().parent.glob("*.py"))
    for path in paths:
        compile(path.read_bytes(), path.name, "exec")
    print(f"PASS Python syntax: {len(paths)} files")


def check_prs():
    rng = random.Random(20261028)
    samples = [
        b"",
        b"A",
        bytes(range(256)),
        b"PSUA synthetic repeated bytes\x00" * 128,
        bytes(rng.randrange(256) for _ in range(2048)),
    ]
    for index, sample in enumerate(samples):
        encoded = prs.prs_compress(sample)
        require(prs.prs_decompress(encoded) == sample, f"PRS sample {index}")
        require(prs.prs_decompress(b"prefix" + encoded, 6) == sample,
                f"PRS start offset {index}")
    print("PASS PRS: 5 synthetic samples and start offsets")


def check_afs():
    payloads = [b"synthetic entry A", bytes(range(256)) * 9, b"tail entry"]
    tail = b"synthetic filename table"
    for pair_mode in (False, True):
        blob = afs.pack(payloads, pair_mode, tail)
        entries, parsed_pair, tail_offset = afs.parse(blob)
        require(parsed_pair == pair_mode, "AFS mode changed")
        require(len(entries) == len(payloads), "AFS entry count changed")
        extracted = [blob[start:start + size] for start, size in entries]
        for original, actual in zip(payloads, extracted):
            if pair_mode:
                require(actual == original, "MiniAFS entry bytes changed")
            else:
                # Offset-only AFS entries include their alignment padding.
                require(actual[:len(original)] == original, "AFS payload changed")
                require(not any(actual[len(original):]), "AFS nonzero padding")
        require(blob[tail_offset:] == tail, "AFS tail changed")
        require(afs.pack(extracted, parsed_pair, blob[tail_offset:]) == blob,
                "AFS parsed/repacked bytes changed")
    print("PASS AFS/MiniAFS: entries, mode, padding, tail and byte roundtrip")


def synthetic_text(strings, group_starts, tail):
    table_start = 12 + 4 * len(group_starts)
    descriptors = [table_start + 4 * i for i in group_starts]
    encoded = [value.encode("utf-16-le") + b"\0\0" for value in strings]
    offsets = []
    position = table_start + 4 * len(strings)
    for value in encoded:
        offsets.append(position)
        position += len(value)
    return (struct.pack("<III", position + len(tail), 8, table_start)
            + b"".join(struct.pack("<I", value) for value in descriptors + offsets)
            + b"".join(encoded) + tail)


def check_text():
    originals = ["Synthetic %s", "", "自造样例\n第二行", "标记\uf820"]
    translated = ["示例 %s", "空槽", "短句", "标记\uf820 保留"]
    tail = b"\x13\x37\x00\x00"
    for groups in ([], [0, 2]):
        blob = synthetic_text(originals, groups, tail)
        parsed = text_tool.parse(blob)
        require(parsed["strs"] == originals, "UTF-16 source strings")
        require(text_tool.build(parsed, originals) == blob, "UTF-16 byte roundtrip")
        changed = text_tool.parse(text_tool.build(parsed, translated))
        require(changed["strs"] == translated, "UTF-16 replacement strings")
        require(changed["tail"] == tail, "UTF-16 tail changed")
        require([(value - changed["T"]) // 4 for value in changed["descs"]] == groups,
                "UTF-16 group boundaries changed")
        require(changed["size"] == len(changed["raw"]), "UTF-16 declared size")
    print("PASS UTF-16 text: grouped/ungrouped, variable lengths, PUA and tail")


def main():
    check_syntax()
    check_prs()
    check_afs()
    check_text()
    print("PASS all resource-free smoke checks")


if __name__ == "__main__":
    main()
