r"""Recover the old English Zone meshes' material slots (StaticMaterials) without property mappings.

Unversioned FStaticMaterial elements serialize MaterialInterface (FPackageIndex, omitted when null),
MaterialSlotName and ImportedMaterialSlotName (FName = name index + number). We scan the start of the
export for FName pairs and the import reference that precedes a pair.

    python mesh_slots.py <extracted root> <mod_imports.json> <out.json>
"""
import json, os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import zen51

SKIP_NAMES = {"BlockAll", "Anomaly", "NoCollision", "BodySetup", "NavCollision", "PhysicsBody", "Foundation"}


def slots_for(base, pkg, imports):
    h = zen51.package_header(open(base + ".uheader", "rb").read())
    names = h["names"]
    imap = imports[pkg]["import_map"]
    d = open(base + ".uexp", "rb").read()
    hits = []                                  # (offset, kind, value)
    o = 0
    limit = min(len(d) - 8, 0x400)
    while o < limit:
        i, n = struct.unpack_from("<ii", d, o)
        if 0 <= i < len(names) and n == 0 and names[i] not in SKIP_NAMES and not names[i].startswith("/"):
            hits.append((o, "name", names[i])); o += 8; continue
        if -len(imap) <= i < 0 and isinstance(imap[-i - 1], str) and imap[-i - 1].startswith("/"):
            hits.append((o, "import", imap[-i - 1])); o += 4; continue
        o += 1
    slots = []
    k = 0
    pending_import = None
    while k < len(hits):
        off, kind, val = hits[k]
        if kind == "import":
            pending_import = val; k += 1; continue
        if k + 1 < len(hits) and hits[k + 1][1] == "name" and hits[k + 1][0] == off + 8:
            slots.append(dict(slot=val, imported=hits[k + 1][2], material=pending_import))
            pending_import = None
            k += 2
            continue
        k += 1
    return slots


def main():
    root, imports_path, out = sys.argv[1:4]
    imports = json.load(open(imports_path))
    res = {}
    for dp, _, fs in os.walk(root):
        for f in sorted(fs):
            if f.startswith("SM_") and f.endswith(".uexp"):
                base = os.path.join(dp, f[:-5])
                rel = os.path.relpath(base, root).replace("\\", "/")
                pkg = "/Game/" + rel[len("Stalker2/Content/"):]
                res[pkg] = slots_for(base, pkg, imports)
    json.dump(res, open(out, "w"), indent=1)
    for k, v in res.items():
        print(k.split("/")[-1], [(s["slot"], s["imported"], (s["material"] or "NULL").split("/")[-1]) for s in v])


main()
