r"""Export the top stored mip of every cooked UE 5.1 Texture2D in an extracted IoStore tree to DDS.

rbwadle's English Zone paks (Nexus 1559) are unversioned (no property tags) and we have no 5.1 mappings,
so this skips the property block: it anchors on the FTexturePlatformData pixel-format
FString ("PF_BC7" etc.) and parses the native data from there (UE 5.1 layout).
Handles regular mips (inline or .ubulk) and streaming virtual textures (RawGPU tiles,
Morton order, borders cropped). Output is block-compressed DDS the editor can import.

    python export_textures.py <extracted root> <dds out root> [--report report.tsv]

Run with the kit's Python (Engine\Binaries\ThirdParty\Python3\Win64\python.exe).
"""
import os, re, struct, sys

# pixel format -> (block bytes, block dim, DDS key: FourCC str, DXGI int, or "BGRA")
FORMATS = {
    "PF_DXT1": (8, 4, "DXT1"),
    "PF_DXT5": (16, 4, "DXT5"),
    "PF_BC4": (8, 4, 80),        # DXGI_FORMAT_BC4_UNORM
    "PF_BC5": (16, 4, 83),       # DXGI_FORMAT_BC5_UNORM
    "PF_BC7": (16, 4, 98),       # DXGI_FORMAT_BC7_UNORM
    "PF_B8G8R8A8": (4, 1, "BGRA"),
    "PF_G8": (1, 1, "L8"),
}

PF_RE = re.compile(rb"(.{4})(PF_[A-Za-z0-9_]+)\x00", re.S)


def blocks(fmt, w, h):
    _, dim, _ = FORMATS[fmt]
    return max(1, (w + dim - 1) // dim), max(1, (h + dim - 1) // dim)


def dds(fmt, w, h, data):
    bb, dim, key = FORMATS[fmt]
    flags = 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000       # CAPS HEIGHT WIDTH PIXELFORMAT LINEARSIZE
    hdr = struct.pack("<4sIIIIIII", b"DDS ", 124, flags, h, w, len(data), 0, 1) + b"\0" * 44
    dx10 = b""
    if key == "BGRA":
        pf = struct.pack("<II4sIIIII", 32, 0x41, b"\0\0\0\0", 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    elif key == "L8":
        pf = struct.pack("<II4sIIIII", 32, 0x20000, b"\0\0\0\0", 8, 0xFF, 0, 0, 0)
    elif isinstance(key, str):
        pf = struct.pack("<II4sIIIII", 32, 0x4, key.encode(), 0, 0, 0, 0, 0)
    else:
        pf = struct.pack("<II4sIIIII", 32, 0x4, b"DX10", 0, 0, 0, 0, 0)
        dx10 = struct.pack("<IIIII", key, 3, 0, 1, 0)   # format, TEXTURE2D, misc, arraySize, misc2
    hdr += pf + struct.pack("<IIIII", 0x1000, 0, 0, 0, 0)
    return hdr + dx10 + data


class R:
    def __init__(self, d, o): self.d, self.o = d, o
    def u32(self): v = struct.unpack_from("<I", self.d, self.o)[0]; self.o += 4; return v
    def i32(self): v = struct.unpack_from("<i", self.d, self.o)[0]; self.o += 4; return v
    def i64(self): v = struct.unpack_from("<q", self.d, self.o)[0]; self.o += 8; return v
    def u8(self): v = self.d[self.o]; self.o += 1; return v
    def arr(self): n = self.i32(); v = list(struct.unpack_from(f"<{n}I", self.d, self.o)); self.o += 4 * n; return v
    def fstr(self):
        n = self.i32()
        if n < 0: s = self.d[self.o:self.o - 2 * n].decode("utf-16-le"); self.o += -2 * n
        else: s = self.d[self.o:self.o + n].decode("latin1"); self.o += n
        return s.rstrip("\0")

    def bulk(self, ubulk):
        """FByteBulkData (cooked, 5.1). Returns payload bytes or None."""
        flags = self.u32()
        if flags & 0x2000:
            count, size = self.i64(), self.i64()
        else:
            count, size = self.i32(), self.i32()
        offset = self.i64()
        if flags & 0x20:                            # BULKDATA_Unused
            return None
        if flags & 0x100:                           # PayloadInSeperateFile -> .ubulk
            if flags & 0x800:
                raise ValueError("optional payload (.uptnl) not in container")
            return ubulk[offset:offset + size] if ubulk is not None else None
        data = self.d[self.o:self.o + size]; self.o += size
        return data


def morton_decode(a):
    def compact(x):
        x &= 0x55555555
        x = (x | (x >> 1)) & 0x33333333
        x = (x | (x >> 2)) & 0x0F0F0F0F
        x = (x | (x >> 4)) & 0x00FF00FF
        x = (x | (x >> 8)) & 0x0000FFFF
        return x
    return compact(a), compact(a >> 1)


def tile_offset(tod, address):
    width, height, maxaddr, addrs, offs = tod
    lo, hi = 0, len(addrs)                          # upper_bound(addrs, address) - 1
    while lo < hi:
        mid = (lo + hi) // 2
        if addrs[mid] <= address: lo = mid + 1
        else: hi = mid
    i = lo - 1
    if offs[i] == 0xFFFFFFFF:
        return None
    return offs[i] + (address - addrs[i])


def parse_vt(r, ubulk):
    r.u32()                                         # bCooked
    num_layers = r.u32()
    r.u32(); r.u32()                                # WidthInBlocks, HeightInBlocks
    tile_size, border = r.u32(), r.u32()
    tile_data_offset_per_layer = r.arr()
    num_mips, width, height = r.u32(), r.u32(), r.u32()
    chunk_index_per_mip = r.arr()
    base_offset_per_mip = r.arr()
    tods = []
    for _ in range(r.i32()):
        w, h, m = r.u32(), r.u32(), r.u32()
        tods.append((w, h, m, r.arr(), r.arr()))
    tile_index_per_chunk = r.arr()
    tile_index_per_mip = r.arr()
    tile_offset_in_chunk = r.arr()
    layer_fmts = [r.fstr() for _ in range(num_layers)]
    r.o += 16 * num_layers                          # LayerFallbackColors
    chunks = []
    for _ in range(r.i32()):
        r.o += 20                                   # BulkDataHash
        size_in_bytes, codec_payload_size = r.u32(), r.u32()
        codecs = []
        for _ in range(num_layers):
            codecs.append((r.u8(), r.u32()))
        chunks.append((codecs, r.bulk(ubulk)))
    if tile_offset_in_chunk:
        raise ValueError("legacy (compressed) VT tile layout")
    fmt = layer_fmts[0]
    if fmt not in FORMATS:
        raise ValueError(f"unsupported VT layer format {fmt}")
    codecs, data = chunks[chunk_index_per_mip[0]]
    if codecs[0][0] != 4:
        raise ValueError(f"VT codec {codecs[0][0]} (not RawGPU)")
    if data is None:
        raise ValueError("VT mip 0 chunk has no payload")
    bb, dim, _ = FORMATS[fmt]
    tile_px = tile_size + 2 * border
    tbw, tbh = blocks(fmt, tile_px, tile_px)
    tile_bytes = tbw * tbh * bb
    tile_data_size = tile_data_offset_per_layer[-1]
    if num_layers == 1 and tile_bytes != tile_data_size:
        raise ValueError(f"tile size mismatch {tile_bytes} vs {tile_data_size}")
    bw, bh = blocks(fmt, width, height)
    bord_b, inner_b = border // dim, tile_size // dim
    out = bytearray(bw * bh * bb)
    tod = tods[0]
    base = base_offset_per_mip[0]
    for ty in range(tod[1]):
        for tx in range(tod[0]):
            a = 0
            for bit in range(16):
                a |= ((tx >> bit) & 1) << (2 * bit) | ((ty >> bit) & 1) << (2 * bit + 1)
            t = tile_offset(tod, a)
            if t is None:
                continue
            src = base + t * tile_data_size
            for row in range(inner_b):
                y = ty * inner_b + row
                if y >= bh: break
                ncols = min(inner_b, bw - tx * inner_b)
                s = src + ((row + bord_b) * tbw + bord_b) * bb
                dsto = (y * bw + tx * inner_b) * bb
                out[dsto:dsto + ncols * bb] = data[s:s + ncols * bb]
    return fmt, width, height, bytes(out), num_layers


def parse(uexp, ubulk):
    m = None
    for c in PF_RE.finditer(uexp):
        if struct.unpack("<i", c.group(1))[0] == len(c.group(2)) + 1:
            m = c
            break
    if not m:
        raise ValueError("no pixel format string")
    fmt = m.group(2).decode()
    size_x, size_y, packed = struct.unpack_from("<iiI", uexp, m.start() - 12)
    r = R(uexp, m.end())
    if packed & (1 << 30):                          # HasOptData
        r.o += 8
    r.i32()                                         # FirstMipToSerialize
    num_mips = r.i32()
    mips = []
    for _ in range(num_mips):
        data = r.bulk(ubulk)
        w, h, _ = r.i32(), r.i32(), r.i32()
        mips.append((w, h, data))
    is_virtual = r.u32()
    if is_virtual:
        vfmt, w, h, data, layers = parse_vt(r, ubulk)
        return vfmt, size_x, size_y, w, h, data, f"VT{layers}"
    if fmt not in FORMATS:
        raise ValueError(f"unsupported {fmt}")
    w, h, data = next(mp for mp in mips if mp[2])
    bw, bh = blocks(fmt, w, h)
    if len(data) != bw * bh * FORMATS[fmt][0]:
        raise ValueError(f"mip {w}x{h} has {len(data)} bytes")
    return fmt, size_x, size_y, w, h, data, "mips"


def main():
    src, dst = sys.argv[1], sys.argv[2]
    report = sys.argv[sys.argv.index("--report") + 1] if "--report" in sys.argv else None
    rows, ok, bad = [], 0, 0
    for dp, _, fs in os.walk(src):
        for f in sorted(fs):
            if not (f.startswith("T_") and f.endswith(".uexp")):
                continue
            base = os.path.join(dp, f[:-5])
            rel = os.path.relpath(base, src).replace("\\", "/")
            try:
                uexp = open(base + ".uexp", "rb").read()
                ubulk = open(base + ".ubulk", "rb").read() if os.path.exists(base + ".ubulk") else None
                fmt, sx, sy, w, h, data, kind = parse(uexp, ubulk)
                out = os.path.join(dst, rel + ".dds")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                open(out, "wb").write(dds(fmt, w, h, data))
                rows.append(f"{rel}\t{fmt}\t{kind}\t{sx}x{sy}\t{w}x{h}\tok")
                ok += 1
            except Exception as e:
                rows.append(f"{rel}\t\t\t\t\tFAIL {type(e).__name__}: {e}")
                bad += 1
    if report:
        open(report, "w", encoding="utf-8").write("path\tformat\tkind\tsize\texported\tstatus\n" + "\n".join(rows) + "\n")
    print(f"exported {ok}, failed {bad}")
    for row in rows:
        if "FAIL" in row:
            print(row)


main()
