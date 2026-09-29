r"""Quick PNG preview of a DXT1 / BGRA DDS written by export_textures.py (stdlib only, downscaled).

    python dds_preview.py <in.dds> <out.png> [--max 512]
"""
import struct, sys, zlib


def rgb565(c):
    return ((c >> 11) & 31) * 255 // 31, ((c >> 5) & 63) * 255 // 63, (c & 31) * 255 // 31


def decode(path):
    d = open(path, "rb").read()
    h, w = struct.unpack_from("<II", d, 12)
    fourcc = d[84:88]
    px = bytearray(w * h * 3)
    if fourcc == b"DXT1":
        o = 128
        for by in range(h // 4):
            for bx in range(w // 4):
                c0, c1, bits = struct.unpack_from("<HHI", d, o); o += 8
                a, b = rgb565(c0), rgb565(c1)
                if c0 > c1:
                    pal = [a, b, tuple((2 * x + y) // 3 for x, y in zip(a, b)), tuple((x + 2 * y) // 3 for x, y in zip(a, b))]
                else:
                    pal = [a, b, tuple((x + y) // 2 for x, y in zip(a, b)), (0, 0, 0)]
                for i in range(16):
                    c = pal[(bits >> (2 * i)) & 3]
                    x, y = bx * 4 + (i & 3), by * 4 + (i >> 2)
                    p = (y * w + x) * 3
                    px[p:p + 3] = bytes(c)
    elif struct.unpack_from("<I", d, 80)[0] & 0x40:          # BGRA
        o = 128
        for i in range(w * h):
            b, g, r, _ = d[o + 4 * i:o + 4 * i + 4]
            px[3 * i:3 * i + 3] = bytes((r, g, b))
    else:
        raise SystemExit(f"unsupported {fourcc}")
    return w, h, px


def png(path, w, h, px):
    raw = b"".join(b"\0" + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    chunk = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


w, h, px = decode(sys.argv[1])
mx = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 512
s = max(1, max(w, h) // mx)
if s > 1:
    nw, nh = w // s, h // s
    small = bytearray(nw * nh * 3)
    for y in range(nh):
        for x in range(nw):
            q = ((y * s) * w + x * s) * 3
            small[(y * nw + x) * 3:(y * nw + x) * 3 + 3] = px[q:q + 3]
    w, h, px = nw, nh, small
png(sys.argv[2], w, h, px)
print(f"{w}x{h}")
