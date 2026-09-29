r"""Reader for cooked UE 5.1 StaticMesh render data (unversioned, no mappings needed).

Skips the property block by scanning for the FStaticMeshLODResources layout:
    StripFlags(2) | Sections[n] (40 B each) | MaxDeviation f32 | bIsLODCookedOut u32 | bInlined u32
    inlined  -> SerializeBuffers: StripFlags(2) | PositionVB | StaticMeshVB | ColorVB | IndexBuffer ...
    streamed -> the same SerializeBuffers block lives in the .ubulk
Used by export_meshes.py.
"""
import struct


class Buf:
    def __init__(self, d, o=0): self.d, self.o = d, o
    def u32(self): v = struct.unpack_from("<I", self.d, self.o)[0]; self.o += 4; return v
    def i32(self): v = struct.unpack_from("<i", self.d, self.o)[0]; self.o += 4; return v
    def f32(self): v = struct.unpack_from("<f", self.d, self.o)[0]; self.o += 4; return v
    def skip(self, n): self.o += n
    def bulk_array(self):
        """TArray::BulkSerialize: int32 element size, int32 count, raw bytes."""
        esize, count = self.i32(), self.i32()
        if esize < 0 or count < 0 or esize * count > len(self.d) - self.o:
            raise ValueError("bad bulk array")
        data = self.d[self.o:self.o + esize * count]; self.o += esize * count
        return esize, count, data


def read_sections(b):
    n = b.i32()
    if not 1 <= n <= 64:
        raise ValueError("section count")
    secs = []
    for _ in range(n):
        mat, first, ntri, vmin, vmax = struct.unpack_from("<iIIII", b.d, b.o); b.o += 20
        flags = struct.unpack_from("<5I", b.d, b.o); b.o += 20
        if any(f > 1 for f in flags) or vmin > vmax or not 0 <= mat < 64 or ntri == 0 or first % 3:
            raise ValueError("section")
        secs.append(dict(material=mat, first=first, ntri=ntri, vmin=vmin, vmax=vmax))
    return secs


def read_buffers(b):
    """FStaticMeshLODResources::SerializeBuffers up to the index buffer."""
    b.skip(2)                                           # StripFlags
    stride, nverts = b.u32(), b.u32()                   # FPositionVertexBuffer
    es, cnt, pos = b.bulk_array()
    if stride != 12 or es != 12 or cnt != nverts:
        raise ValueError("position buffer")
    positions = [struct.unpack_from("<3f", pos, 12 * i) for i in range(nverts)]
    b.skip(2)                                           # FStaticMeshVertexBuffer strip flags
    ntex, nv2 = b.u32(), b.u32()
    full_uv, hp_tan = b.u32(), b.u32()
    if nv2 != nverts or not 1 <= ntex <= 8 or full_uv > 1 or hp_tan > 1:
        raise ValueError("static mesh vertex buffer")
    es, cnt, tan = b.bulk_array()
    tsize = 16 if hp_tan else 8
    if es * cnt != tsize * nverts:
        raise ValueError("tangents")
    es, cnt, uvd = b.bulk_array()
    usize = 8 if full_uv else 4
    if es * cnt != usize * ntex * nverts:
        raise ValueError("uvs")
    b.skip(2)                                           # FColorVertexBuffer strip flags
    cstride, cverts = b.u32(), b.u32()
    colors = None
    if cverts:
        es, cnt, cd = b.bulk_array()
        colors = [tuple(cd[4 * i:4 * i + 4]) for i in range(cverts)]   # FColor = B G R A
    is32 = b.u32()
    es, cnt, idx = b.bulk_array()
    fmt = "<I" if is32 else "<H"
    isz = 4 if is32 else 2
    indices = [struct.unpack_from(fmt, idx, isz * i)[0] for i in range(len(idx) // isz)]

    def unpack_normal(raw, i):                          # FPackedNormal: uint8 -> [-1,1]
        return tuple((x - 127.5) / 127.5 for x in raw[i:i + 4])

    def unpack_rgba16n(raw, i):
        return tuple(v / 32767.0 for v in struct.unpack_from("<4h", raw, i))

    tangents, normals = [], []
    for i in range(nverts):
        o = i * tsize
        if hp_tan:
            tx, tz = unpack_rgba16n(tan, o), unpack_rgba16n(tan, o + 8)
        else:
            tx, tz = unpack_normal(tan, o), unpack_normal(tan, o + 4)
        tangents.append(tx[:3]); normals.append(tz)       # tz[3] = binormal sign
    uvs = [[None] * nverts for _ in range(ntex)]
    for i in range(nverts):
        for t in range(ntex):
            o = (i * ntex + t) * usize
            if full_uv:
                uvs[t][i] = struct.unpack_from("<2f", uvd, o)
            else:
                uvs[t][i] = struct.unpack_from("<2e", uvd, o)
    return dict(positions=positions, normals=normals, tangents=tangents, uvs=uvs,
                colors=colors, indices=indices, hp_tan=hp_tan, full_uv=full_uv)


def find_lods(uexp):
    """All LOD headers in order: (offset after header, sections, cooked_out, inlined)."""
    lods, o = [], 0
    while o < len(uexp) - 60:
        try:
            b = Buf(uexp, o + 2)
            secs = read_sections(b)
            maxdev = b.f32()
            cooked_out, inlined = b.u32(), b.u32()
            if cooked_out > 1 or inlined > 1 or not (maxdev == maxdev) or abs(maxdev) > 1e6:
                raise ValueError
            if inlined and not cooked_out:
                read_buffers(Buf(uexp, b.o))            # must parse cleanly
            lods.append((b.o, secs, cooked_out, inlined))
            o = b.o
            continue
        except Exception:
            pass
        o += 1
    return lods


def read_mesh(uexp, ubulk):
    """Returns list of LODs: dict(sections=..., **buffers). Streamed LODs are taken from the .ubulk in order."""
    out = []
    bulk_pos = 0
    for off, secs, cooked_out, inlined in find_lods(uexp):
        if cooked_out:
            continue
        if inlined:
            geo = read_buffers(Buf(uexp, off))
        else:
            if ubulk is None:
                raise ValueError("streamed LOD but no .ubulk")
            # streamed LOD buffers are stored back to back in the .ubulk, LOD0 first
            geo = None
            for start in range(bulk_pos, min(len(ubulk), bulk_pos + 4096)):
                try:
                    b = Buf(ubulk, start)
                    geo = read_buffers(b)
                    bulk_pos = b.o
                    break
                except Exception:
                    continue
            if geo is None:
                raise ValueError("could not locate streamed LOD in .ubulk")
        nv = len(geo["positions"])
        for s in secs:
            if s["vmax"] >= nv or s["first"] + 3 * s["ntri"] > len(geo["indices"]):
                raise ValueError("section out of range")
        geo["sections"] = secs
        out.append(geo)
    return out
