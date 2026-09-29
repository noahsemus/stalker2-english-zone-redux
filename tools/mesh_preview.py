r"""Orthographic flat-shaded preview of a decoded mesh (front view along -Y), stdlib only.

    python mesh_preview.py <mesh dir under work/extracted> <out.png> [--axis y] [--size 1024]
Uses the Nanite leaf geometry if present, else the LOD0 render data.
"""
import os, struct, sys, zlib
sys.path.insert(0, os.path.dirname(__file__))
import nanite51, sm51


def load(base):
    u = open(base + ".uexp", "rb").read()
    ub = open(base + ".ubulk", "rb").read() if os.path.exists(base + ".ubulk") else b""
    r, _ = nanite51.find_resources(u, len(ub))
    if r:
        g = nanite51.NaniteMesh(r, ub).extract()
        return g["positions"], g["triangles"]
    lod = sm51.read_mesh(u, ub or None)[0]
    idx = lod["indices"]
    return lod["positions"], [tuple(idx[i:i + 3]) for i in range(0, len(idx), 3)]


def render(pos, tris, size, axis):
    # view axis: project onto the other two (horizontal, vertical=Z unless axis == z)
    ax = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}[axis]
    va = {"x": 0, "y": 1, "z": 2}[axis]
    hs = [p[ax[0]] for p in pos]; vs = [p[ax[1]] for p in pos]
    mnh, mxh, mnv, mxv = min(hs), max(hs), min(vs), max(vs)
    sc = (size - 20) / max(mxh - mnh, mxv - mnv, 1e-6)
    w, h = int((mxh - mnh) * sc) + 20, int((mxv - mnv) * sc) + 20
    img = bytearray(b"\x20" * (w * h * 3))
    depth = [float("-inf")] * (w * h)
    for a, b, c in tris:
        P = [pos[a], pos[b], pos[c]]
        e1 = [P[1][i] - P[0][i] for i in range(3)]; e2 = [P[2][i] - P[0][i] for i in range(3)]
        n = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0])
        ln = (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5 or 1
        shade = int(60 + 190 * abs(n[va]) / ln)
        pts = [((p[ax[0]] - mnh) * sc + 10, h - ((p[ax[1]] - mnv) * sc + 10), -p[va]) for p in P]
        x0, x1 = int(max(0, min(q[0] for q in pts))), int(min(w - 1, max(q[0] for q in pts)) + 1)
        y0, y1 = int(max(0, min(q[1] for q in pts))), int(min(h - 1, max(q[1] for q in pts)) + 1)
        (ax_, ay_, az_), (bx_, by_, bz_), (cx_, cy_, cz_) = pts
        den = (by_ - cy_) * (ax_ - cx_) + (cx_ - bx_) * (ay_ - cy_)
        if abs(den) < 1e-9:
            continue
        for y in range(y0, y1):
            for x in range(x0, x1):
                l1 = ((by_ - cy_) * (x - cx_) + (cx_ - bx_) * (y - cy_)) / den
                l2 = ((cy_ - ay_) * (x - cx_) + (ax_ - cx_) * (y - cy_)) / den
                l3 = 1 - l1 - l2
                if l1 < 0 or l2 < 0 or l3 < 0:
                    continue
                z = l1 * az_ + l2 * bz_ + l3 * cz_
                i = y * w + x
                if z > depth[i]:
                    depth[i] = z
                    img[3 * i:3 * i + 3] = bytes((shade, shade, shade))
    return w, h, img


def png(path, w, h, px):
    raw = b"".join(b"\0" + bytes(px[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    ch = lambda t, b: struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xFFFFFFFF)
    open(path, "wb").write(b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + ch(b"IDAT", zlib.compress(raw, 6)) + ch(b"IEND", b""))


if __name__ == "__main__":
    axis = sys.argv[sys.argv.index("--axis") + 1] if "--axis" in sys.argv else "y"
    size = int(sys.argv[sys.argv.index("--size") + 1]) if "--size" in sys.argv else 1024
    pos, tris = load(sys.argv[1])
    w, h, img = render(pos, tris, size, axis)
    png(sys.argv[2], w, h, img)
    print(w, h, len(tris))
