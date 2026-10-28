#!/usr/bin/env python3
"""bin2iso.py — 将 chdman extractcd 得到的 RAW (2352字节/扇区) MODE1 BIN 转为 2048 字节扇区的 ISO。

用法:
    python bin2iso.py <input.bin> <output.iso>

PS2 DVD 为 MODE1 扇区: 12 同步字节 + 4 头部 + 2048 用户数据 + 288 EDC/ECC。
本脚本逐扇区校验同步字与模式字节，抽取用户数据区。
"""
import sys
import os

RAW_SECTOR = 2352
USER_DATA = 2048
SYNC = b"\x00" + b"\xff" * 10 + b"\x00"


def main(src: str, dst: str) -> None:
    total = os.path.getsize(src)
    if total % RAW_SECTOR:
        print(f"警告: 文件大小 {total} 不是 {RAW_SECTOR} 的整数倍，可能不是 RAW BIN")
    sectors = total // RAW_SECTOR
    bad = 0
    with open(src, "rb") as f, open(dst, "wb") as out:
        for i in range(sectors):
            sec = f.read(RAW_SECTOR)
            if len(sec) < RAW_SECTOR:
                break
            if sec[:12] != SYNC or sec[15] != 1:
                bad += 1
                # 模式异常时仍抽取数据区，但保持字节对齐
            out.write(sec[16:16 + USER_DATA])
            if (i + 1) % 100000 == 0:
                print(f"  {i + 1}/{sectors} 扇区...")
    print(f"完成: {sectors} 扇区, 异常扇区 {bad}, 输出 {os.path.getsize(dst)} 字节")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
