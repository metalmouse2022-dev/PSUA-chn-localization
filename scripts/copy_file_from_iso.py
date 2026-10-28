#!/usr/bin/env python3
"""copy_file_from_iso.py — 从 ISO 流式复制大文件。
用法: python copy_file_from_iso.py <iso> <iso内路径> <输出>
"""
import sys
import pycdlib

CHUNK = 4 << 20


def main():
    iso_path, inner, out = sys.argv[1:4]
    iso = pycdlib.PyCdlib()
    iso.open(iso_path)
    with iso.open_file_from_iso(iso_path=inner) as fp, open(out, "wb") as f:
        fp.seek(0)
        while True:
            b = fp.read(CHUNK)
            if not b:
                break
            f.write(b)
    iso.close()
    import os
    print("OK", out, os.path.getsize(out))


if __name__ == "__main__":
    main()
