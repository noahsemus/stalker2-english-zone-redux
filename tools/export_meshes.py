r"""Decode every cooked UE 5.1 StaticMesh in an extracted tree to a JSON geometry file for the editor rebuild.

Nanite meshes: full-detail leaf clusters (nanite51). Non-Nanite: every LOD from the render data (sm51).
Output per mesh: <out>/<package path>.json with
    {"nanite": bool, "lods": [{"positions", "normals", "colors", "uvs": [...], "triangles", "materials"}]}
positions in cm (UE space), triangles as vertex index triples, materials = section/material slot index per triangle.

    python export_meshes.py <extracted root> <out root> [--report report.tsv] [--only NAME]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import nanite51, sm51


def lod_from_render(lod):
    idx = lod["indices"]
    tris, mats = [], []
    for s in lod["sections"]:
        for t in range(s["ntri"]):
            i = s["first"] + 3 * t
            tris.append(idx[i:i + 3]); mats.append(s["material"])
    colors = [(c[2], c[1], c[0], c[3]) for c in lod["colors"]] if lod["colors"] else None   # BGRA -> RGBA
    return dict(positions=lod["positions"], normals=[n[:3] for n in lod["normals"]], colors=colors,
                uvs=lod["uvs"], triangles=tris, materials=mats)


def export(base):
    u = open(base + ".uexp", "rb").read()
    ub = open(base + ".ubulk", "rb").read() if os.path.exists(base + ".ubulk") else b""
    r, _ = nanite51.find_resources(u, len(ub))
    if r:
        g = nanite51.NaniteMesh(r, ub).extract()
        if len(g["triangles"]) != r["num_input_triangles"]:
            raise ValueError(f"nanite leaf tris {len(g['triangles'])} != input {r['num_input_triangles']}")
        if any(m is None for m in g["materials"]):
            raise ValueError("triangle without material range")
        has_color = bool(r["resource_flags"] & 1)
        lod = dict(positions=g["positions"], normals=g["normals"], colors=g["colors"] if has_color else None,
                   uvs=g["uvs"], triangles=g["triangles"], materials=g["materials"])
        return dict(nanite=True, lods=[lod]), f"nanite {len(g['triangles'])} tris, {len(g['uvs'])} uv"
    lods = [lod_from_render(l) for l in sm51.read_mesh(u, ub or None)]
    if not lods:
        raise ValueError("no render data found")
    return dict(nanite=False, lods=lods), f"{len(lods)} lods, lod0 {len(lods[0]['triangles'])} tris"


def main():
    src, dst = sys.argv[1], sys.argv[2]
    report = sys.argv[sys.argv.index("--report") + 1] if "--report" in sys.argv else None
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    rows, ok, bad = [], 0, 0
    for dp, _, fs in os.walk(src):
        for f in sorted(fs):
            if not (f.startswith("SM_") and f.endswith(".uexp")) or (only and only not in f):
                continue
            base = os.path.join(dp, f[:-5])
            rel = os.path.relpath(base, src).replace("\\", "/")
            try:
                data, info = export(base)
                out = os.path.join(dst, rel + ".json")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                json.dump(data, open(out, "w"), separators=(",", ":"))
                rows.append(f"{rel}\t{info}\tok"); ok += 1
            except Exception as e:
                rows.append(f"{rel}\t\tFAIL {type(e).__name__}: {e}"); bad += 1
            print(rows[-1], flush=True)
    if report:
        open(report, "w", encoding="utf-8").write("path\tinfo\tstatus\n" + "\n".join(rows) + "\n")
    print(f"exported {ok}, failed {bad}")


if __name__ == "__main__":
    main()
