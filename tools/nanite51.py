r"""Locate and decode UE 5.1 Nanite::FResources from a cooked StaticMesh (.uexp + .ubulk).

Decoding follows the 5.1 engine: NaniteEncode.cpp (writer) and NaniteDataDecode.ush /
NaniteAttributeDecode.ush (reader). Only the leaf clusters (full-detail level) are emitted.
"""
import struct


class Buf:
    def __init__(self, d, o=0): self.d, self.o = d, o
    def u16(self): v = struct.unpack_from("<H", self.d, self.o)[0]; self.o += 2; return v
    def u32(self): v = struct.unpack_from("<I", self.d, self.o)[0]; self.o += 4; return v
    def i32(self): v = struct.unpack_from("<i", self.d, self.o)[0]; self.o += 4; return v
    def i64(self): v = struct.unpack_from("<q", self.d, self.o)[0]; self.o += 8; return v

    def arr(self, esize, limit=1 << 26):
        n = self.i32()
        if not 0 <= n <= limit or self.o + n * esize > len(self.d):
            raise ValueError("array")
        data = self.d[self.o:self.o + n * esize]; self.o += n * esize
        return n, data


def try_resources(uexp, o, ubulk_len):
    """Parse FResources at o (StripFlags first). Returns dict or raises."""
    b = Buf(uexp, o)
    b.o += 2                                        # StripFlags
    flags = b.u32()
    if flags > 7:
        raise ValueError("resource flags")
    bflags = b.u32()
    if bflags & 0x2000:
        count, size = b.i64(), b.i64()
    else:
        count, size = b.i32(), b.i32()
    offset = b.i64()
    if bflags & 0x20:                               # unused (no streaming pages)
        size = 0
    elif not (bflags & 0x100):
        raise ValueError("pages must live in .ubulk")
    elif not (0 < size and 0 <= offset and offset + size <= ubulk_len):
        raise ValueError("bulk range")
    nroot, root = b.arr(1)
    nstates, states = b.arr(24)
    nnodes, nodes = b.arr(208)
    nroots, rootoffs = b.arr(4)
    ndeps, deps = b.arr(4)
    nimp, imp = b.arr(2)
    num_root_pages, pos_prec = b.u32(), b.i32()
    ntri, nvert = b.u32(), b.u32()
    nmesh, ntex = b.u16(), b.u16()
    nclusters = b.u32()
    if not (1 <= num_root_pages <= nstates and nroot > 0 and ntri > 0 and nvert > 0 and 1 <= ntex <= 4 and nclusters > 0):
        raise ValueError("counts")
    return dict(end=b.o, resource_flags=flags, bulk_offset=offset, bulk_size=size, root=root,
                states=[struct.unpack_from("<6I", states, 24 * i) for i in range(nstates)],
                num_root_pages=num_root_pages, pos_precision=pos_prec, num_input_triangles=ntri,
                num_input_vertices=nvert, num_input_meshes=nmesh, num_tex=ntex, num_clusters=nclusters,
                deps=[struct.unpack_from("<I", deps, 4 * i)[0] for i in range(ndeps)])


def find_resources(uexp, ubulk_len):
    for o in range(len(uexp) - 64):
        try:
            return try_resources(uexp, o, ubulk_len), o
        except Exception:
            continue
    return None, None


# ---------------------------------------------------------------- page decoding

M32 = 0xFFFFFFFF


def u32at(d, o):
    return struct.unpack_from("<I", d, o)[0]


def read_bits(d, bitpos, n):
    if n == 0:
        return 0
    s = bitpos >> 3
    e = (bitpos + n + 7) >> 3
    v = int.from_bytes(d[s:e + 1], "little") >> (bitpos & 7)
    return v & ((1 << n) - 1)


def bfe_u(x, n, s):
    return (x >> s) & ((1 << n) - 1)


def bfe_i(x, s):                                    # 1-bit signed extract: -1 or 0
    return -1 if (x >> s) & 1 else 0


def popc(x):
    return bin(x & M32).count("1")


def read_unaligned_dword(d, base, bitoff):
    if bitoff < 0:
        return (u32at(d, base) << (8 - (bitoff & 7))) & M32
    o = base + (bitoff >> 3)
    return (int.from_bytes(d[o:o + 4].ljust(4, b"\0"), "little") >> (bitoff & 7)) & M32


def unpack_strip(d, strip_off, idx_base, nprev_ref_dw, nprev_new_dw, tri):
    """Port of UnpackTriangleIndices (NaniteEncode.cpp, 5.1)."""
    dw, bit = tri >> 5, tri & 31
    S, L, W = struct.unpack_from("<3I", d, strip_off + dw * 12)
    SL = S & L
    head_ref = (SL | (~S & M32)) & W
    prev_mask = (1 << bit) - 1
    nref_before = bfe_u(nprev_ref_dw, 10, dw * 10 - 10) if dw else 0
    nnew_before = bfe_u(nprev_new_dw, 10, dw * 10 - 10) if dw else 0
    cur_ref = (popc(SL & prev_mask) << 1) + popc(W & prev_mask)
    cur_new = (popc(S & prev_mask) << 1) + bit - cur_ref
    nref = nref_before + cur_ref
    nnew = nnew_before + cur_new
    is_start, is_left, is_ref = bfe_i(S, bit), bfe_i(L, bit), bfe_i(W, bit)
    base_vertex = nnew - 1
    data = read_unaligned_dword(d, idx_base, (nref + (~is_start)) * 5)
    out = [0, 0, 0]
    if is_start:
        minus_nref = (is_left << 1) + is_ref
        nxt = nnew
        if minus_nref <= -1:
            out[0] = base_vertex - (data & 31); data >>= 5
        else:
            out[0] = nxt; nxt += 1
        if minus_nref <= -2:
            out[1] = base_vertex - (data & 31); data >>= 5
        else:
            out[1] = nxt; nxt += 1
        if minus_nref <= -3:
            out[2] = base_vertex - (data & 31)
        else:
            out[2] = nxt; nxt += 1
    else:
        pb = bit - 1
        is_prev_start = bfe_i(S, pb)
        is_prev_head_ref = bfe_i(head_ref, pb)
        nprev_new_in_tri = is_prev_start & (3 - ((bfe_u(L, 1, pb) << 1) | bfe_u(W, 1, pb)))
        out[1] = base_vertex + (is_prev_head_ref & (nprev_new_in_tri - (data & 31)))
        out[2] = nnew + (is_ref & (-1 - bfe_u(data, 5, 5)))
        search = (S | (L ^ (is_left & M32))) & M32
        found = (search & prev_mask).bit_length() - 1
        is_found_s = bfe_i(S, found)
        fmask = (1 << found) - 1
        f_cur_ref = (popc(SL & fmask) << 1) + popc(W & fmask)
        f_cur_new = (popc(S & fmask) << 1) + found - f_cur_ref
        f_new = nnew_before + f_cur_new
        f_ref = nref_before + f_cur_ref
        f_nrefv = (bfe_u(L, 1, found) << 1) + bfe_u(W, 1, found)
        is_before_found_ref = bfe_u(head_ref, 1, found - 1) if found >= 1 else 0
        read_off = is_left if is_found_s else 1
        fdata = read_unaligned_dword(d, idx_base, (f_ref - read_off) * 5)
        f_index = (f_new - 1) - bfe_u(fdata, 5, 0)
        cond = (f_nrefv >= 1 - is_left) if is_found_s else (is_before_found_ref != 0)
        f_newv = f_new + ((is_left & (1 if f_nrefv == 0 else 0)) if is_found_s else -1)
        out[0] = f_index if cond else f_newv
        if is_left:
            out[1], out[2] = out[2], out[1]
    return out


def octa_decode(x, y, bits=9):
    m = (1 << bits) - 1
    fx, fy = x * (2.0 / m) - 1.0, y * (2.0 / m) - 1.0
    fz = 1.0 - abs(fx) - abs(fy)
    t = min(max(-fz, 0.0), 1.0)
    fx += -t if fx >= 0 else t
    fy += -t if fy >= 0 else t
    ln = (fx * fx + fy * fy + fz * fz) ** 0.5 or 1.0
    return (fx / ln, fy / ln, fz / ln)


class Page:
    """One Nanite page (fixup chunk + disk page). Decodes clusters to logical vertices."""

    def __init__(self, raw):
        nclu, nhier, ncfix, _ = struct.unpack_from("<4H", raw, 0)
        o = 8 + nhier * 16
        self.cluster_fixups = [struct.unpack_from("<2I", raw, o + 8 * i) for i in range(ncfix)]
        d = raw[o + ncfix * 8:]
        self.d = d
        (self.gpu_size, self.nclusters, self.raw_f4, self.ntex, self.nvrefs,
         self.decode_info_off, self.strip_off, self.vref_bitmask_off) = struct.unpack_from("<8I", d, 0)
        if self.nclusters != nclu:
            raise ValueError("page header mismatch")
        self.gpu_base = 32 + 32 * self.nclusters
        self._packed = {}
        self.coded = {}
        self.full = {}

    def disk_header(self, c):
        return struct.unpack_from("<8I", self.d, 32 + 32 * c)

    def packed(self, c):
        if c in self._packed:
            return self._packed[c]
        n = self.nclusters
        f4 = [struct.unpack_from("<4I", self.d, self.gpu_base + 16 + (k * n + c) * 16) for k in range(7)]
        p = {}
        p["num_verts"] = bfe_u(f4[0][0], 9, 0)
        p["num_tris"] = bfe_u(f4[0][1], 8, 0)
        p["color_min"] = f4[0][2]
        p["color_bits"] = bfe_u(f4[0][3], 16, 0)
        p["pos_start"] = struct.unpack("<3i", struct.pack("<3I", *f4[1][:3]))
        w = f4[1][3]
        p["pos_prec"] = bfe_u(w, 5, 4) - 8
        p["pos_bits"] = (bfe_u(w, 5, 9), bfe_u(w, 5, 14), bfe_u(w, 5, 19))
        p["flags"] = f4[4][3]
        p["bits_per_attr"] = bfe_u(f4[5][0], 10, 22)
        p["num_uvs"] = bfe_u(f4[5][1], 3, 22)
        p["color_mode"] = bfe_u(f4[5][1], 2, 25)
        p["uv_prec"] = f4[5][2]
        p["material"] = f4[5][3]
        self._packed[c] = p
        return p

    def uv_ranges(self, c):
        out = []
        base = self.decode_info_off + c * self.ntex * 32
        for t in range(self.ntex):
            mnx, mny, gsx, gsy, glx, gly, prec, _ = struct.unpack_from("<2i4IiI", self.d, base + t * 32)
            out.append(((mnx, mny), (gsx, gsy), (glx, gly), prec))
        return out

    def decode_coded(self, c):
        """Coded (non-reference) vertices of cluster c: list of (qpos, normal, color, uvs)."""
        if c in self.coded:
            return self.coded[c]
        p = self.packed(c)
        dh = self.disk_header(c)
        pos_off, attr_off, nvrefs = dh[3], dh[4], dh[5]
        ncoded = p["num_verts"] - nvrefs
        bx, by, bz = p["pos_bits"]
        pstride = (bx + by + bz + 7) & ~7
        astride = (p["bits_per_attr"] + 7) & ~7
        cb = [bfe_u(p["color_bits"], 4, 4 * i) for i in range(4)]
        cmin = [bfe_u(p["color_min"], 8, 8 * i) for i in range(4)]
        ranges = self.uv_ranges(c)
        ps = p["pos_start"]
        verts = []
        for j in range(ncoded):
            bp = (pos_off << 3) + j * pstride
            q = (read_bits(self.d, bp, bx), read_bits(self.d, bp + bx, by), read_bits(self.d, bp + bx + by, bz))
            ap = (attr_off << 3) + j * astride
            nrm = read_bits(self.d, ap, 18); ap += 18
            normal = octa_decode(nrm & 511, nrm >> 9)
            col = []
            for i in range(4):
                col.append(cmin[i] + read_bits(self.d, ap, cb[i])); ap += cb[i]
            if p["color_mode"] == 0:
                col = [255, 255, 255, 255]
            uvs = []
            for t in range(self.ntex):
                ub, vb = bfe_u(p["uv_prec"], 4, t * 8), bfe_u(p["uv_prec"], 4, t * 8 + 4)
                packed = read_bits(self.d, ap, ub + vb); ap += ub + vb
                pu, pv = packed & ((1 << ub) - 1), packed >> ub
                (mnx, mny), (gsx, gsy), (glx, gly), prec = ranges[t]
                tu = pu + (glx if pu > gsx else 0)
                tv = pv + (gly if pv > gsy else 0)
                sc = 2.0 ** -prec
                uvs.append(((tu + mnx) * sc, (tv + mny) * sc))
            verts.append(((q[0] + ps[0], q[1] + ps[1], q[2] + ps[2]), normal, tuple(col), uvs))
        self.coded[c] = verts
        return verts

    def triangles(self, c):
        p = self.packed(c)
        dh = self.disk_header(c)
        strip_off = self.strip_off + c * (128 // 32) * 12
        return [unpack_strip(self.d, strip_off, dh[0], dh[6], dh[7], t) for t in range(p["num_tris"])]

    def materials(self, c):
        p = self.packed(c)
        enc = p["material"]
        n = p["num_tris"]
        if enc < 0xFE000000:
            m0, m1, m2 = bfe_u(enc, 6, 0), bfe_u(enc, 6, 6), bfe_u(enc, 6, 12)
            l0, l1 = bfe_u(enc, 7, 18) + 1, bfe_u(enc, 7, 25)
            return [m0 if t < l0 else (m1 if t < l0 + l1 else m2) for t in range(n)]
        off, ln = bfe_u(enc, 19, 0), bfe_u(enc, 6, 19) + 1
        mats = [None] * n
        for i in range(ln):
            e = u32at(self.d, self.gpu_base + (off + i) * 4)
            s, l, m = bfe_u(e, 8, 0), bfe_u(e, 8, 8), bfe_u(e, 6, 16)
            for t in range(s, min(n, s + l)):
                mats[t] = m
        return mats


class NaniteMesh:
    def __init__(self, res, ubulk):
        self.res = res
        self.pages = []
        for i, st in enumerate(res["states"]):
            bulk_off, bulk_size = st[0], st[1]
            if i < res["num_root_pages"]:
                raw = res["root"][bulk_off:bulk_off + bulk_size]
            else:
                o = res["bulk_offset"] + bulk_off
                raw = ubulk[o:o + bulk_size]
            self.pages.append(Page(raw))

    def full_vertices(self, pi, c):
        """All vertices of cluster c in page pi (refs resolved)."""
        page = self.pages[pi]
        if c in page.full:
            return page.full[c]
        p = page.packed(c)
        dh = page.disk_header(c)
        coded = page.decode_coded(c)
        bm_off = page.vref_bitmask_off + c * 32
        bitmask = int.from_bytes(page.d[bm_off:bm_off + 32], "little")
        state = self.res["states"][pi]
        out = []
        nref = ncoded = 0
        for v in range(p["num_verts"]):
            if (bitmask >> v) & 1:
                hi = page.d[dh[2] + nref]                           # page-cluster map index
                lo = page.d[dh[2] + nref + page.nvrefs]             # vertex index
                pcd = u32at(page.d, dh[1] + hi * 4)
                parent, src_c = pcd >> 8, pcd & 0xFF
                if parent == 0:
                    out.append(page.decode_coded(src_c)[lo])
                else:
                    dep = self.res["deps"][state[3] + parent - 1]
                    out.append(self.full_vertices(dep, src_c)[lo])
                nref += 1
            else:
                out.append(coded[ncoded]); ncoded += 1
        page.full[c] = out
        return out

    def leaf_clusters(self):
        cleared = set()
        for page in self.pages:
            for pc, _ in page.cluster_fixups:
                cleared.add((pc >> 8, pc & 0xFF))
        out = []
        for pi, page in enumerate(self.pages):
            for c in range(page.nclusters):
                if page.packed(c)["flags"] & 1 and (pi, c) not in cleared:
                    out.append((pi, c))
        return out

    def extract(self):
        """Leaf geometry: positions (cm), normals, colors, uv sets, triangles, per-triangle material."""
        prec = None
        verts, tris, mats = [], [], []
        for pi, c in self.leaf_clusters():
            page = self.pages[pi]
            p = page.packed(c)
            if prec is None:
                prec = p["pos_prec"]
            elif prec != p["pos_prec"]:
                raise ValueError("mixed position precision")
            fv = self.full_vertices(pi, c)
            base = len(verts)
            verts.extend(fv)
            for t, m in zip(page.triangles(c), page.materials(c)):
                if max(t) >= len(fv) or min(t) < 0:
                    raise ValueError(f"bad index in page {pi} cluster {c}: {t}")
                tris.append((base + t[0], base + t[1], base + t[2]))
                mats.append(m)
        sc = 2.0 ** -prec
        return dict(positions=[(q[0] * sc, q[1] * sc, q[2] * sc) for q, _, _, _ in verts],
                    qpositions=[q for q, _, _, _ in verts],
                    normals=[n for _, n, _, _ in verts], colors=[col for _, _, col, _ in verts],
                    uvs=[[v[3][t] for v in verts] for t in range(self.res["num_tex"])],
                    triangles=tris, materials=mats)
