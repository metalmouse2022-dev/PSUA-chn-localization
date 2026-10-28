#!/usr/bin/env python3
"""prs.py — SEGA PRS Legacy 变体解压器与简单压缩器。

参考: tools/prs_src (rust-ages-prs, MIT)。本实现沿用 PSU/PSULib
的 Legacy 长拷贝语义：size 字段为 0 时，后续长度字节加 1。
"""


def prs_decompress(data: bytes, start: int = 0) -> bytes:
    """从 data[start] 开始解压 PRS 流，直到 EOF 命令或数据耗尽。"""
    out = bytearray()
    pos = start
    cmds = 0
    rem = 0

    def bit():
        nonlocal cmds, rem, pos
        if rem == 0:
            if pos >= len(data):
                raise EOFError("PRS 流意外结束")
            cmds = data[pos]
            pos += 1
            rem = 8
        ret = cmds & 1
        cmds >>= 1
        rem -= 1
        return ret

    while True:
        try:
            if bit():
                # 字面字节
                if pos >= len(data):
                    raise EOFError
                out.append(data[pos])
                pos += 1
                continue
            if bit():
                # 长拷贝 (2字节偏移)
                if pos + 1 >= len(data):
                    raise EOFError
                raw = data[pos] | (data[pos + 1] << 8)
                pos += 2
                if raw == 0:
                    break  # EOF
                size = raw & 7
                off = raw - 0x10000 if raw >= 0x8000 else raw  # 符号扩展
                off >>= 3  # 算术右移
                if size == 0:
                    size = data[pos] + 1  # PSU/PSULib 变体（Legacy, rust-ages-prs 命名）
                    pos += 1
                else:
                    size += 2
                back = 8192 - (off & 0x1FFF)
            else:
                # 短拷贝 (1字节偏移)
                b1 = bit()
                b2 = bit()
                size = (b2 | (b1 << 1)) + 2
                if pos >= len(data):
                    raise EOFError
                back = 256 - data[pos] if data[pos] else 256
                pos += 1
            if back <= 0 or back > len(out):
                raise ValueError(f"非法回引 back={back} @out={len(out)} pos={pos:#x}")
            for _ in range(size):
                out.append(out[-back])
        except EOFError:
            break
    return bytes(out)


def prs_compress(src: bytes) -> bytes:
    """PRS 压缩（哈希链匹配 + 朴素回退，Legacy 变体终止）。"""
    out = bytearray()
    cmd_pos = 0
    cmd_bits_left = 8
    n = len(src)
    i = 0

    def put_bit(b):
        nonlocal cmd_pos, cmd_bits_left
        if cmd_bits_left == 8:
            out.append(0)
            cmd_pos = len(out) - 1
        if b:
            out[cmd_pos] |= 1 << (8 - cmd_bits_left)
        cmd_bits_left -= 1
        if cmd_bits_left == 0:
            cmd_bits_left = 8

    # 3 字节 / 2 字节前缀 -> 位置列表（哈希链加速匹配）
    from collections import defaultdict
    table = defaultdict(list)
    table2 = defaultdict(list)

    def find_match(pos, max_len):
        best_len = 0
        best_back = 0
        best_gain = -999
        lo = max(0, pos - 8191)
        if max_len < 2 or pos + 1 >= n:
            return 0, 0
        if pos + 2 < n:
            key = (src[pos] << 16) | (src[pos + 1] << 8) | src[pos + 2]
            cands = table[key]
            checked = 0
            for j in reversed(cands):
                if j < lo:
                    break
                checked += 1
                if checked > 512:
                    break
                back = pos - j
                l = 3
                while l < max_len and src[j + l] == src[pos + l]:
                    l += 1

                # 计算比 literal (9 bit/byte) 节省的比特数
                if 2 <= l <= 5 and back <= 255:
                    gain = l * 9 - 12
                elif l <= 9:
                    gain = l * 9 - 18
                else:
                    gain = l * 9 - 26

                if gain > best_gain or (gain == best_gain and l > best_len):
                    best_gain = gain
                    best_len = l
                    best_back = back
                    if l >= max_len:
                        break

        # 2 字节候选检查（当无 3 字节匹配，或 3 字节增益较小且距离远时，优先选近距离 2 字节短拷贝）
        if best_len < 3 or (best_gain < 6 and best_back > 255):
            key2 = (src[pos] << 8) | src[pos + 1]
            cands2 = table2[key2]
            checked = 0
            for j in reversed(cands2):
                if j < lo:
                    break
                checked += 1
                if checked > 128:
                    break
                back = pos - j
                if back <= 255:
                    l = 2
                    while l < max_len and src[j + l] == src[pos + l]:
                        l += 1
                    gain = l * 9 - 12
                    if gain > best_gain:
                        best_gain = gain
                        best_len = l
                        best_back = back
                        if l >= 5:
                            break

        if best_gain <= 0:
            return 0, 0
        return best_len, best_back

    while i < n:
        max_len = min(n - i, 256)
        best_len, best_back = find_match(i, max_len)
        # 登记当前位置供后续匹配
        if i + 2 < n:
            table[(src[i] << 16) | (src[i + 1] << 8) | src[i + 2]].append(i)
        if i + 1 < n:
            table2[(src[i] << 8) | src[i + 1]].append(i)
        if 2 <= best_len <= 5 and best_back <= 255:
            put_bit(0)
            put_bit(0)
            put_bit((best_len - 2) >> 1)
            put_bit((best_len - 2) & 1)
            out.append(256 - best_back)
            # 登记被跳过的位置
            for k in range(i + 1, i + best_len):
                if k + 2 < n:
                    table[(src[k] << 16) | (src[k + 1] << 8) | src[k + 2]].append(k)
                if k + 1 < n:
                    table2[(src[k] << 8) | src[k + 1]].append(k)
            i += best_len
        elif best_len >= 3:
            put_bit(0)
            put_bit(1)
            if best_len <= 9:
                sz = best_len - 2
                ext = None
            else:
                sz = 0
                ext = best_len - 1
            off_field = (8192 - best_back) & 0x1FFF
            raw = (off_field << 3) | sz
            out.append(raw & 0xFF)
            out.append((raw >> 8) & 0xFF)
            if ext is not None:
                out.append(ext)
            for k in range(i + 1, i + best_len):
                if k + 2 < n:
                    table[(src[k] << 16) | (src[k + 1] << 8) | src[k + 2]].append(k)
                if k + 1 < n:
                    table2[(src[k] << 8) | src[k + 1]].append(k)
            i += best_len
        else:
            put_bit(1)
            out.append(src[i])
            i += 1
    # EOF: 长拷贝 offset=0
    put_bit(0)
    put_bit(1)
    out.append(0)
    out.append(0)
    return bytes(out)


if __name__ == "__main__":
    import sys
    d = open(sys.argv[1], "rb").read()
    off = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0
    out = prs_decompress(d, off)
    sys.stdout.buffer.write(out)
