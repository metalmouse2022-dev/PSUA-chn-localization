import gzip, struct

elf = gzip.decompress(open('work/elf/PSU.GZ', 'rb').read())
print(f'PSU.elf size: {len(elf)}')

candidates = []
for base in range(0x00000000, 0x00400000, 0x10):
    for toff in [0xA0, 0]:
        off = (0x0029C300 - base) + toff
        if 0 <= off < len(elf) - 4:
            w = struct.unpack_from('<I', elf, off)[0]
            if (w & 0xFFFF) == 0x882D or ((w >> 16) & 0xFFFF) == 0x882D:
                # verify with weapon enhance at 0x004DEA74
                off_enh = (0x004DEA74 - base) + toff
                if 0 <= off_enh < len(elf) - 4:
                    w_enh = struct.unpack_from('<I', elf, off_enh)[0]
                    # D04DEA76 00001020 means *(u16*)(0x004DEA74 + 2) == 0x1020 or *(u16*)(0x004DEA76) == 0x1020
                    if (w_enh >> 16) == 0x1020 or (w_enh & 0xFFFF) == 0x1020:
                        candidates.append((base, toff, w, w_enh))

print(f'Matching candidates: {len(candidates)}')
for base, toff, w, w_enh in candidates:
    off_inv = (0x0044559C - base) + toff
    w_inv = struct.unpack_from('<I', elf, off_inv)[0] if 0 <= off_inv < len(elf)-4 else 0
    print(f'Base 0x{base:08X} (toff=0x{toff:X}): exp=0x{w:08X}, enh=0x{w_enh:08X}, inv=0x{w_inv:08X}')
