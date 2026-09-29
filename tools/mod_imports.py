r"""Resolve what each package of rbwadle's English Zone (Nexus 1559) container imports (package names).

    python mod_imports.py <mod .ucas> <container header offset> <size> <extracted root> <package_ids.json> <out.json>
Writes {"/Game/...": {"imports": [...names], "import_map": [...], "names": [...]}} for every package.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import zen51


def main():
    ucas, off, size, root, ids_path, out = sys.argv[1:7]
    with open(ucas, "rb") as f:
        f.seek(int(off)); ch = zen51.container_header(f.read(int(size)))
    ids = {int(k): v for k, v in json.load(open(ids_path)).items()}
    result = {}
    for dp, _, fs in os.walk(root):
        for fn in fs:
            if not fn.endswith(".uheader"):
                continue
            rel = os.path.relpath(os.path.join(dp, fn[:-8]), root).replace("\\", "/")
            if rel.startswith("Stalker2/Content/"):
                cooked = "/EnglishZone/" + rel[len("Stalker2/Content/"):]
                game = "/Game/" + rel[len("Stalker2/Content/"):]
            else:
                parts = rel.split("/"); i = parts.index("Content")
                cooked = game = "/" + parts[i - 1] + "/" + "/".join(parts[i + 1:])
            pid = zen51.package_id(cooked)
            hdr = zen51.package_header(open(os.path.join(dp, fn), "rb").read())
            imported = [ids.get(x, hex(x)) for x in ch.get(pid, [])]
            imap = []
            for v in hdr["imports"]:
                kind = v >> 62
                if v == (1 << 64) - 1:
                    imap.append(None)
                elif kind == 1:
                    imap.append("script")
                elif kind == 2:
                    pkg = (v >> 32) & 0x3FFFFFFF
                    imap.append(imported[pkg] if pkg < len(imported) else f"pkg#{pkg}")
                else:
                    imap.append(hex(v))
            result[game] = dict(imports=imported, import_map=imap, names=hdr["names"])
    json.dump(result, open(out, "w"), indent=1)
    unresolved = sorted({x for r in result.values() for x in r["imports"] if x.startswith("0x")})
    print(len(result), "packages;", len(unresolved), "unresolved import ids")


main()
