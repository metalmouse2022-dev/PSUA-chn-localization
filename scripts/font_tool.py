#!/usr/bin/env python3
"""font_tool.py — PSU DE_FONT 字库工具（sega.bin + segafon.bin）。

格式（已逆向验证）:
  sega.bin:   8312 × 3 字节 = (BE16 Unicode 码点, u8 像素宽度)
  segafon.bin: 8312 × 64 字节字形, 16x16 像素 2bpp(4级灰度),
               每行 4 字节, 字节内 MSB 优先, 行主序

用法:
  python font_tool.py sheet <sega> <segafon> <输出.png>     # 导出字形总表
  python font_tool.py demo <sega> <segafon> <文本> <png>    # 用原字库渲染文本
  python font_tool.py cnfont <sega> <segafon> <字表> <输出前缀>  # 生成中文字形替换字库
"""
import sys

from PIL import Image, ImageDraw, ImageFont

GLYPH_W, GLYPH_H = 16, 16
LEVELS = (0, 85, 170, 255)  # 2bpp -> 8bit 灰度


def load(sega_path, fon_path):
    sega = open(sega_path, "rb").read()
    fon = open(fon_path, "rb").read()
    assert len(sega) % 3 == 0 and len(fon) // 64 == len(sega) // 3, "表与字形数不匹配"
    n = len(sega) // 3
    entries = [((sega[i * 3] << 8) | sega[i * 3 + 1], sega[i * 3 + 2]) for i in range(n)]
    return entries, fon


def glyph_to_image(cell: bytes) -> Image.Image:
    img = Image.new("L", (GLYPH_W, GLYPH_H), 0)
    px = img.load()
    for r in range(GLYPH_H):
        for c in range(GLYPH_W):
            b = cell[r * 4 + (c >> 2)]
            v = (b >> (6 - 2 * (c & 3))) & 3
            px[c, r] = LEVELS[v]
    return img


def image_to_glyph(img: Image.Image) -> bytes:
    """把 16x16 灰度图量化为 2bpp 字形"""
    img = img.convert("L").resize((GLYPH_W, GLYPH_H))
    cell = bytearray(64)
    px = img.load()
    for r in range(GLYPH_H):
        for c in range(GLYPH_W):
            # 量化到 0..3
            v = min(3, (px[c, r] * 4 + 128) // 256)
            cell[r * 4 + (c >> 2)] |= v << (6 - 2 * (c & 3))
    return bytes(cell)


def render_text(entries, fon, text, font_scale=2):
    """用字库渲染一行文本（预览用）"""
    codes = [e[0] for e in entries]
    scale = font_scale
    W = sum(entries[codes.index(ord(ch))][1] if ord(ch) in codes else 8 for ch in text) * scale + 8
    img = Image.new("L", (W, GLYPH_H * scale + 8), 255)
    x = 2
    for ch in text:
        cp = ord(ch)
        if cp not in codes:
            cp = 0x25AF  # ▯ 占位
            if cp not in codes:
                continue
        idx = codes.index(cp)
        w = entries[idx][1]
        g = glyph_to_image(fon[idx * 64:(idx + 1) * 64])
        g = g.resize((w * scale, GLYPH_H * scale), Image.NEAREST)
        inv = g.point(lambda v: 255 - v)  # 黑字白底
        img.paste(inv, (x, 4))
        x += w * scale
    return img


def export_sheet(entries, fon, out_png, cols=32):
    from PIL import Image as I
    n = len(entries)
    rows = (n + cols - 1) // cols
    sheet = I.new("L", (cols * 18, rows * 18), 60)
    for i, (code, _w) in enumerate(entries):
        g = glyph_to_image(fon[i * 64:(i + 1) * 64])
        sheet.paste(g, ((i % cols) * 18 + 1, (i // cols) * 18 + 1))
    sheet.save(out_png)
    print(f"字形总表 {n} 字 -> {out_png}")


def build_chinese_font(sega_path, fon_path, charset, ttf_path, out_prefix,
                       size=16, replace_threshold=0x0500):
    """为字符集生成中文字形并写回字库。

    替换策略：优先复用同码点槽位；否则替换"冷门汉字"槽位
    （码点 >= replace_threshold 的 JIS 生僻字按从后往前替换）。
    """
    entries, fon = load(sega_path, fon_path)
    entries = [list(e) for e in entries]
    fon = bytearray(fon)
    codes = {e[0]: i for i, e in enumerate(entries)}
    # 待替换槽位: 从表尾往前找生僻汉字槽（非 ASCII/假名/常用符号）
    free_slots = [i for i, (c, w) in enumerate(entries)
                  if 0x4E00 <= c <= 0x9FFF and c not in charset]
    free_ptr = len(free_slots) - 1
    font = ImageFont.truetype(ttf_path, size)
    used = 0
    for ch in charset:
        cp = ord(ch)
        # 画到 16x16（左上角起，全角字符满宽）
        img = Image.new("L", (GLYPH_W, GLYPH_H), 0)
        draw = ImageDraw.Draw(img)
        bbox = draw.textbbox((0, 0), ch, font=font)
        # 居中
        ox = (GLYPH_W - (bbox[2] - bbox[0])) // 2 - bbox[0]
        oy = (GLYPH_H - (bbox[3] - bbox[1])) // 2 - bbox[1]
        draw.text((ox, oy), ch, font=font, fill=255)
        cell = image_to_glyph(img)
        if cp in codes:
            idx = codes[cp]
        else:
            if free_ptr < 0:
                print(f"!! 槽位耗尽: {ch} U+{cp:04X}")
                continue
            idx = free_slots[free_ptr]
            free_ptr -= 1
            entries[idx] = [cp, GLYPH_W]
            codes[cp] = idx
        fon[idx * 64:(idx + 1) * 64] = cell
        used += 1
    sega_out = bytearray()
    for c, w in entries:
        sega_out += bytes([(c >> 8) & 0xFF, c & 0xFF, w])
    open(out_prefix + ".sega.bin", "wb").write(sega_out)
    open(out_prefix + ".segafon.bin", "wb").write(bytes(fon))
    print(f"中文字形 {used} 个已生成 -> {out_prefix}.sega.bin/.segafon.bin")


def append_chinese_font(sega_path, fon_path, charset, ttf_path, fallback_ttf, out_prefix,
                        size=16):
    """扩表模式：保留全部原字形与宽度，将缺失的中文字按码点序插入表中。

    与 replace 模式不同，本模式不动任何原有槽位 —— 日文文本零风险。
    ttf 缺字形（渲染为空）时用 fallback_ttf 补。
    """
    import bisect
    entries, fon = load(sega_path, fon_path)
    entries = [list(e) for e in entries]
    fon = bytearray(fon)
    codes = [e[0] for e in entries]
    font = ImageFont.truetype(ttf_path, size)
    fb_font = ImageFont.truetype(fallback_ttf, size) if fallback_ttf else None

    missing = sorted(cp for cp in charset if cp not in set(codes))
    added = 0
    empty_fixed = 0
    for cp in missing:
        cell = None
        for fnt in (font, fb_font):
            if fnt is None:
                continue
            img = Image.new("L", (GLYPH_W, GLYPH_H), 0)
            draw = ImageDraw.Draw(img)
            bbox = draw.textbbox((0, 0), chr(cp), font=fnt)
            ox = (GLYPH_W - (bbox[2] - bbox[0])) // 2 - bbox[0]
            oy = (GLYPH_H - (bbox[3] - bbox[1])) // 2 - bbox[1]
            draw.text((ox, oy), chr(cp), font=fnt, fill=255)
            cell = image_to_glyph(img)
            if any(cell):
                if fnt is fb_font:
                    empty_fixed += 1
                break
        if cell is None or not any(cell):
            continue  # 两套字体都无字形，跳过（后续报告）
        idx = bisect.bisect_left(codes, cp)
        codes.insert(idx, cp)
        entries.insert(idx, [cp, GLYPH_W])
        fon[idx * 64:idx * 64] = cell  # 零宽切片插入（后续字形右移）
        added += 1
    sega_out = bytearray()
    for c, w in entries:
        sega_out += bytes([(c >> 8) & 0xFF, c & 0xFF, w])
    open(out_prefix + ".sega.bin", "wb").write(bytes(sega_out))
    open(out_prefix + ".segafon.bin", "wb").write(bytes(fon))
    print(f"扩表: 原始 {len(entries) - added} + 新增 {added} = {len(entries)} 字形 "
          f"(zpix缺字用unifont补 {empty_fixed} 个)")


def main():
    cmd = sys.argv[1]
    if cmd == "sheet":
        entries, fon = load(sys.argv[2], sys.argv[3])
        export_sheet(entries, fon, sys.argv[4])
    elif cmd == "demo":
        entries, fon = load(sys.argv[2], sys.argv[3])
        img = render_text(entries, fon, sys.argv[4])
        img.save(sys.argv[5])
        print("渲染 ->", sys.argv[5])
    elif cmd == "cnappend":
        charset = set(ord(c) for c in open(sys.argv[4], encoding="utf-8").read().strip())
        append_chinese_font(sys.argv[2], sys.argv[3], charset, sys.argv[5],
                            sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] != "-" else None,
                            sys.argv[7] if len(sys.argv) > 7 else "work/cn_font2")
    elif cmd == "cnfont":
        charset = open(sys.argv[4], encoding="utf-8").read().strip()
        charset = "".join(dict.fromkeys(charset))  # 去重
        build_chinese_font(sys.argv[2], sys.argv[3], set(charset), sys.argv[5],
                           sys.argv[6] if len(sys.argv) > 6 else "work/cn_font")
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
