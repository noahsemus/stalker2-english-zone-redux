r"""UE 5.1 zen package / container helpers: package ids (CityHash64), package summary, name map,
import map, and the container header's per-package imported-package lists."""
import struct

M64 = (1 << 64) - 1
K0, K1, K2 = 0xc3a5c85c97cb3127, 0xb492b66fbe98f273, 0x9ae16a3b2f90404f
KMUL = 0x9ddfea08eb382d69


def _f64(s, o): return struct.unpack_from("<Q", s, o)[0]
def _f32(s, o): return struct.unpack_from("<I", s, o)[0]
def _rot(v, n): return v if n == 0 else ((v >> n) | (v << (64 - n))) & M64
def _smix(v): return v ^ (v >> 47)
def _bswap(v): return int.from_bytes(v.to_bytes(8, "little"), "big")


def _h16(u, v, mul=KMUL):
    a = ((u ^ v) * mul) & M64; a ^= a >> 47
    b = ((v ^ a) * mul) & M64; b ^= b >> 47
    return (b * mul) & M64


def _h0to16(s, n):
    if n >= 8:
        mul = (K2 + n * 2) & M64
        a = (_f64(s, 0) + K2) & M64
        b = _f64(s, n - 8)
        c = (_rot(b, 37) * mul + a) & M64
        d = ((_rot(a, 25) + b) * mul) & M64
        return _h16(c, d, mul)
    if n >= 4:
        mul = (K2 + n * 2) & M64
        a = _f32(s, 0)
        return _h16((n + (a << 3)) & M64, _f32(s, n - 4), mul)
    if n > 0:
        a, b, c = s[0], s[n >> 1], s[n - 1]
        y = a + (b << 8); z = n + (c << 2)
        return (_smix(((y * K2) ^ (z * K0)) & M64) * K2) & M64
    return K2


def _h17to32(s, n):
    mul = (K2 + n * 2) & M64
    a = (_f64(s, 0) * K1) & M64
    b = _f64(s, 8)
    c = (_f64(s, n - 8) * mul) & M64
    d = (_f64(s, n - 16) * K2) & M64
    return _h16((_rot((a + b) & M64, 43) + _rot(c, 30) + d) & M64, (a + _rot((b + K2) & M64, 18) + c) & M64, mul)


def _weak(w, x, y, z, a, b):
    a = (a + w) & M64
    b = _rot((b + a + z) & M64, 21)
    c = a
    a = (a + x + y) & M64
    b = (b + _rot(a, 44)) & M64
    return ((a + z) & M64, (b + c) & M64)


def _weak_s(s, o, a, b):
    return _weak(_f64(s, o), _f64(s, o + 8), _f64(s, o + 16), _f64(s, o + 24), a, b)


def _h33to64(s, n):
    mul = (K2 + n * 2) & M64
    a = (_f64(s, 0) * K2) & M64
    b = _f64(s, 8)
    c = _f64(s, n - 24)
    d = _f64(s, n - 32)
    e = (_f64(s, 16) * K2) & M64
    f = (_f64(s, 24) * 9) & M64
    g = _f64(s, n - 8)
    h = (_f64(s, n - 16) * mul) & M64
    u = (_rot((a + g) & M64, 43) + (_rot(b, 30) + c) * 9) & M64
    v = (((a + g) ^ d) + f + 1) & M64
    w = (_bswap(((u + v) * mul) & M64) + h) & M64
    x = (_rot((e + f) & M64, 42) + c) & M64
    y = ((_bswap(((v + w) * mul) & M64) + g) * mul) & M64
    z = (e + f + c) & M64
    a = (_bswap(((x + z) * mul + y) & M64) + b) & M64
    b = (_smix(((z + a) * mul + d + h) & M64) * mul) & M64
    return (b + x) & M64


def cityhash64(s):
    n = len(s)
    if n <= 16: return _h0to16(s, n)
    if n <= 32: return _h17to32(s, n)
    if n <= 64: return _h33to64(s, n)
    x = _f64(s, n - 40)
    y = (_f64(s, n - 16) + _f64(s, n - 56)) & M64
    z = _h16((_f64(s, n - 48) + n) & M64, _f64(s, n - 24))
    v = _weak_s(s, n - 64, n, z)
    w = _weak_s(s, n - 32, (y + K1) & M64, x)
    x = (x * K1 + _f64(s, 0)) & M64
    ln = (n - 1) & ~63
    o = 0
    while True:
        x = (_rot((x + y + v[0] + _f64(s, o + 8)) & M64, 37) * K1) & M64
        y = (_rot((y + v[1] + _f64(s, o + 48)) & M64, 42) * K1) & M64
        x ^= w[1]
        y = (y + v[0] + _f64(s, o + 40)) & M64
        z = (_rot((z + w[0]) & M64, 33) * K1) & M64
        v = _weak_s(s, o, (v[1] * K1) & M64, (x + w[0]) & M64)
        w = _weak_s(s, o + 32, (z + w[1]) & M64, (y + _f64(s, o + 16)) & M64)
        z, x = x, z
        o += 64; ln -= 64
        if ln == 0:
            break
    return _h16((_h16(v[0], w[0]) + _smix(y) * K1 + z) & M64, (_h16(v[1], w[1]) + x) & M64)


def package_id(name):
    """FPackageId::FromName: CityHash64 of the lower-cased UTF-16 package name ("/Game/...")."""
    return cityhash64(name.lower().encode("utf-16-le"))


def name_batch(d, o):
    num = struct.unpack_from("<I", d, o)[0]; o += 4
    if num == 0:
        return [], o
    o += 4 + 8 + 8 * num
    hdrs = [struct.unpack_from(">H", d, o + 2 * i)[0] for i in range(num)]; o += 2 * num
    out = []
    for h in hdrs:
        ln = h & 0x7FFF
        if h & 0x8000:
            if o % 2: o += 1
            out.append(d[o:o + 2 * ln].decode("utf-16-le")); o += 2 * ln
        else:
            out.append(d[o:o + ln].decode("latin1")); o += ln
    return out, o


def package_header(uheader):
    """5.1 FZenPackageSummary (no versioning info) -> names, import map (u64 list)."""
    d = uheader
    has_ver, header_size = struct.unpack_from("<II", d, 0)
    if has_ver:
        raise ValueError("versioned zen package not supported")
    pub_hashes_off, import_off, export_off = struct.unpack_from("<iii", d, 24)
    names, _ = name_batch(d, 44)
    nimp = (export_off - import_off) // 8
    imports = list(struct.unpack_from(f"<{nimp}Q", d, import_off))
    nhash = (import_off - pub_hashes_off) // 8
    pub_hashes = list(struct.unpack_from(f"<{nhash}Q", d, pub_hashes_off))
    return dict(names=names, imports=imports, imported_public_export_hashes=pub_hashes)


def container_header(data):
    """5.1 FIoContainerHeader -> {package_id: [imported package ids]}."""
    sig, ver = struct.unpack_from("<II", data, 0)
    o = 8 + 8                                                   # signature, version, container id
    n = struct.unpack_from("<i", data, o)[0]; o += 4
    ids = list(struct.unpack_from(f"<{n}Q", data, o)); o += 8 * n
    nb = struct.unpack_from("<i", data, o)[0]; o += 4
    store = data[o:o + nb]
    out = {}
    for i, pid in enumerate(ids):
        e = 24 * i
        exp_count, bundle_count, imp_num, imp_off = struct.unpack_from("<iiII", store, e)
        base = e + 8 + imp_off
        out[pid] = list(struct.unpack_from(f"<{imp_num}Q", store, base))
    return out
