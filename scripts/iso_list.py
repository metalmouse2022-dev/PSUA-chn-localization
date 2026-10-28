#!/usr/bin/env python3
"""iso_list.py — 列出 PS2 ISO 的完整文件树（递归），输出 TSV。"""
import sys
import pycdlib


def main(iso_path, out_path):
    iso = pycdlib.PyCdlib()
    iso.open(iso_path)
    out = []

    def rec(dirpath):
        for child in iso.list_children(iso_path=dirpath):
            if child.is_dot() or child.is_dotdot():
                continue
            name = child.file_identifier().decode("ascii", "replace")
            full = dirpath.rstrip("/") + "/" + name
            if child.is_dir():
                out.append(("DIR", 0, full))
                rec(full)
            else:
                out.append(("FILE", child.get_data_length(), full))

    rec("/")
    iso.close()
    with open(out_path, "w", encoding="utf-8") as f:
        for typ, size, path in out:
            f.write(f"{typ}\t{size}\t{path}\n")
    files = sum(1 for t, _, _ in out if t == "FILE")
    dirs = sum(1 for t, _, _ in out if t == "DIR")
    print(f"共 {files} 个文件, {dirs} 个目录")
    for typ, size, path in out[:60]:
        print(f"{typ}\t{size:>12}\t{path}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
