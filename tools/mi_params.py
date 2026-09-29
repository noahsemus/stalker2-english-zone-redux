r"""Recover MaterialInstanceConstant parameter overrides from the old (unversioned, UE 5.1) cooked MIs.

Scalar / vector / texture parameter arrays are found by trying, at every offset, an int32 count followed by
that many unversioned FScalar/FVector/FTextureParameterValue structs that parse cleanly back to back.

    python mi_params.py <extracted root> <mod_imports.json> <out.json>
"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import zen51


class R:
    def __init__(self, d, o): self.d, self.o = d, o
    def u8(self): v = self.d[self.o]; self.o += 1; return v
    def u16(self): v = struct.unpack_from("<H", self.d, self.o)[0]; self.o += 2; return v
    def i32(self): v = struct.unpack_from("<i", self.d, self.o)[0]; self.o += 4; return v
    def f32(self): v = struct.unpack_from("<f", self.d, self.o)[0]; self.o += 4; return v


def unversioned(r, fields):
    """Read an unversioned struct: fields = [(name, reader(r) -> value, zero_value)] in schema order."""
    frags = []
    while True:
        h = r.u16()
        skip, zeros, last, num = h & 0x7F, (h >> 7) & 1, (h >> 8) & 1, h >> 9
        frags.append((skip, zeros, num))
        if last:
            break
        if len(frags) > 8:
            raise ValueError("too many fragments")
    nz = sum(num for _, z, num in frags if z)
    mask = 0
    if nz:
        nbytes = 1 if nz <= 8 else (2 if nz <= 16 else ((nz + 31) // 32) * 4)
        mask = int.from_bytes(r.d[r.o:r.o + nbytes], "little"); r.o += nbytes
    out = {}
    idx = 0
    zbit = 0
    for skip, zeros, num in frags:
        idx += skip
        for _ in range(num):
            if idx >= len(fields):
                raise ValueError("field index out of range")
            name, reader, zero = fields[idx]
            is_zero = False
            if zeros:
                is_zero = (mask >> zbit) & 1; zbit += 1
            out[name] = zero if is_zero else reader(r)
            idx += 1
    return out


def make_readers(names, imap):
    def fname(r):
        i, n = r.i32(), r.i32()
        if not 0 <= i < len(names) or n != 0:
            raise ValueError("fname")
        return names[i]

    def assoc(r):
        v = r.u8()
        if v > 3: raise ValueError("assoc")
        return v

    def index(r):
        v = r.i32()
        if not -1 <= v < 64: raise ValueError("index")
        return v

    info_fields = [("Name", fname, None), ("Association", assoc, 0), ("Index", index, 0)]
    info = lambda r: unversioned(r, info_fields)
    def guid(r):
        v = r.d[r.o:r.o + 16].hex(); r.o += 16
        return v

    def fl(r):
        v = r.f32()
        if v != v or abs(v) > 1e7: raise ValueError("float")
        return v

    def color(r):
        return [fl(r) for _ in range(4)]

    def tex(r):
        i = r.i32()
        if i == 0: return None
        if not -len(imap) <= i < 0: raise ValueError("texture ref")
        return imap[-i - 1]

    return {
        "scalar": [("ParameterInfo", info, None), ("ParameterValue", fl, 0.0), ("ExpressionGUID", guid, None)],
        "vector": [("ParameterInfo", info, None), ("ParameterValue", color, [0, 0, 0, 0]), ("ExpressionGUID", guid, None)],
        "texture": [("ParameterInfo", info, None), ("ParameterValue", tex, None), ("ExpressionGUID", guid, None)],
    }


def find_arrays(d, readers):
    found = {}
    for kind in ("scalar", "vector", "texture"):
        best = None
        for o in range(0, len(d) - 8):
            n = struct.unpack_from("<i", d, o)[0]
            if not 1 <= n <= 128:
                continue
            r = R(d, o + 4)
            vals = []
            try:
                for _ in range(n):
                    v = unversioned(r, readers[kind])
                    if not v.get("ParameterInfo") or not v["ParameterInfo"].get("Name"):
                        raise ValueError("no name")
                    vals.append(v)
            except Exception:
                continue
            if best is None or n > len(best[1]):
                best = (o, vals)
        if best:
            found[kind] = {v["ParameterInfo"]["Name"]: v["ParameterValue"] for v in best[1]}
    return found


def main():
    root, imports_path, out = sys.argv[1:4]
    imports = json.load(open(imports_path))
    res = {}
    for dp, _, fs in os.walk(root):
        for f in sorted(fs):
            if f.startswith("MI_") and f.endswith(".uexp"):
                base = os.path.join(dp, f[:-5])
                rel = os.path.relpath(base, root).replace("\\", "/")
                pkg = "/Game/" + rel[len("Stalker2/Content/"):]
                names = zen51.package_header(open(base + ".uheader", "rb").read())["names"]
                d = open(base + ".uexp", "rb").read()
                res[pkg] = find_arrays(d, make_readers(names, imports[pkg]["import_map"]))
                res[pkg]["parent_candidates"] = [x for x in imports[pkg]["imports"] if "/MI_" in x or "/M_" in x]
    json.dump(res, open(out, "w"), indent=1)
    for k, v in res.items():
        print(k.split("/")[-1], {t: len(v.get(t, {})) for t in ("scalar", "vector", "texture")})


main()
