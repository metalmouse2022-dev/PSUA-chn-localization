#!/usr/bin/env python3
"""iso_extract.py — 从 PS2 ISO 中提取指定文件。

用法:
    python iso_extract.py <iso> <iso内路径> <输出文件>   # 提取单个文件
    python iso_extract.py <iso> --head <iso内路径> <输出文件> <字节数>  # 只取头部
"""
import sys
import pycdlib


def main():
    args = sys.argv[1:]
    iso = pycdlib.PyCdlib()
    iso.open(args[0])
    try:
        if args[1] == "--head":
            path, out, n = args[2], args[3], int(args[4])
            with open(out, "wb") as f:
                iso.get_file_from_iso_fp(f, iso_path=path, size=n)
        else:
            path, out = args[1], args[2]
            with open(out, "wb") as f:
                iso.get_file_from_iso_fp(f, iso_path=path)
        print(f"OK: {path} -> {out}")
    finally:
        iso.close()


if __name__ == "__main__":
    main()
