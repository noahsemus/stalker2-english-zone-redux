r"""Write decoded mesh JSON (export_meshes.py) as ASCII FBX 7.4 for the Zone Kit's FBX importer.

Positions are UE centimetres. FBX is written Z-up, cm, and with Y negated (UE's importer negates Y back),
winding unchanged (verified: the importer flips it back itself). Normals and every UV set are written per polygon vertex;
one material per slot, named after the slot.

    python write_fbx.py <mesh json> <out.fbx> [--lod N] [--slots name1,name2,...]
    python write_fbx.py --all <meshes root> <out root> <plan.json>
"""
import json, os, sys


def fmt(vals):
    return ",".join(("%.6g" % v) if isinstance(v, float) else str(v) for v in vals)


def fbx_for(lod, slot_names):
    pos, nrm, uvs, tris, mats = lod["positions"], lod["normals"], lod["uvs"], lod["triangles"], lod["materials"]
    cp_index, cps = {}, []
    remap = []
    for p in pos:
        k = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
        if k not in cp_index:
            cp_index[k] = len(cps); cps.append(k)
        remap.append(cp_index[k])
    verts, pvi, normals = [], [], []
    for x, y, z in cps:
        verts += [x, -y, z]
    uv_direct = [[] for _ in uvs]
    uv_index = [[] for _ in uvs]
    uv_maps = [dict() for _ in uvs]
    poly_mats = []
    cols = lod.get("colors")
    colors = []
    for (a, b, c), m in zip(tris, mats):
        corners = (a, b, c)                          # UE winding kept: importer compensates the Y mirror
        for n, i in enumerate(corners):
            idx = remap[i]
            pvi.append(-idx - 1 if n == 2 else idx)
            if cols:
                colors += [c / 255.0 for c in cols[i]]
            nx, ny, nz = nrm[i]
            normals += [nx, -ny, nz]
            for t in range(len(uvs)):
                u, v = uvs[t][i]
                key = (round(u, 6), round(v, 6))
                mp = uv_maps[t]
                if key not in mp:
                    mp[key] = len(mp); uv_direct[t] += [u, 1.0 - v]     # FBX V is bottom-up
                uv_index[t].append(mp[key])
        poly_mats.append(m)
    nslots = max(max(mats) + 1, len(slot_names))
    names = [slot_names[i] if i < len(slot_names) else "Slot%d" % i for i in range(nslots)]

    L = []
    w = L.append
    w("; FBX 7.4.0 project file")
    w("FBXHeaderExtension:  {\n\tFBXHeaderVersion: 1003\n\tFBXVersion: 7400\n\tCreator: \"EnglishZoneRedux write_fbx.py\"\n}")
    w("GlobalSettings:  {\n\tVersion: 1000\n\tProperties70:  {")
    for prop in ["\"UpAxis\", \"int\", \"Integer\", \"\",2", "\"UpAxisSign\", \"int\", \"Integer\", \"\",1",
                 "\"FrontAxis\", \"int\", \"Integer\", \"\",1", "\"FrontAxisSign\", \"int\", \"Integer\", \"\",-1",
                 "\"CoordAxis\", \"int\", \"Integer\", \"\",0", "\"CoordAxisSign\", \"int\", \"Integer\", \"\",1",
                 "\"UnitScaleFactor\", \"double\", \"Number\", \"\",1", "\"OriginalUnitScaleFactor\", \"double\", \"Number\", \"\",1"]:
        w("\t\tP: " + prop)
    w("\t}\n}")
    w("Definitions:  {\n\tVersion: 100\n\tCount: %d" % (3 + nslots))
    w("\tObjectType: \"GlobalSettings\" {\n\t\tCount: 1\n\t}")
    w("\tObjectType: \"Model\" {\n\t\tCount: 1\n\t}")
    w("\tObjectType: \"Geometry\" {\n\t\tCount: 1\n\t}")
    w("\tObjectType: \"Material\" {\n\t\tCount: %d\n\t}\n}" % nslots)
    w("Objects:  {")
    w("\tGeometry: 1000, \"Geometry::Mesh\", \"Mesh\" {")
    w("\t\tVertices: *%d {\n\t\t\ta: %s\n\t\t}" % (len(verts), fmt(verts)))
    w("\t\tPolygonVertexIndex: *%d {\n\t\t\ta: %s\n\t\t}" % (len(pvi), fmt(pvi)))
    w("\t\tGeometryVersion: 124")
    w("\t\tLayerElementNormal: 0 {\n\t\t\tVersion: 101\n\t\t\tName: \"\"\n\t\t\tMappingInformationType: \"ByPolygonVertex\"\n\t\t\tReferenceInformationType: \"Direct\"")
    w("\t\t\tNormals: *%d {\n\t\t\t\ta: %s\n\t\t\t}\n\t\t}" % (len(normals), fmt(normals)))
    if colors:
        w("\t\tLayerElementColor: 0 {\n\t\t\tVersion: 101\n\t\t\tName: \"\"\n\t\t\tMappingInformationType: \"ByPolygonVertex\"\n\t\t\tReferenceInformationType: \"Direct\"")
        w("\t\t\tColors: *%d {\n\t\t\t\ta: %s\n\t\t\t}\n\t\t}" % (len(colors), fmt(colors)))
    for t in range(len(uvs)):
        w("\t\tLayerElementUV: %d {\n\t\t\tVersion: 101\n\t\t\tName: \"UVChannel_%d\"\n\t\t\tMappingInformationType: \"ByPolygonVertex\"\n\t\t\tReferenceInformationType: \"IndexToDirect\"" % (t, t + 1))
        w("\t\t\tUV: *%d {\n\t\t\t\ta: %s\n\t\t\t}" % (len(uv_direct[t]), fmt(uv_direct[t])))
        w("\t\t\tUVIndex: *%d {\n\t\t\t\ta: %s\n\t\t\t}\n\t\t}" % (len(uv_index[t]), fmt(uv_index[t])))
    w("\t\tLayerElementMaterial: 0 {\n\t\t\tVersion: 101\n\t\t\tName: \"\"\n\t\t\tMappingInformationType: \"ByPolygon\"\n\t\t\tReferenceInformationType: \"IndexToDirect\"")
    w("\t\t\tMaterials: *%d {\n\t\t\t\ta: %s\n\t\t\t}\n\t\t}" % (len(poly_mats), fmt(poly_mats)))
    for t in range(max(1, len(uvs))):
        w("\t\tLayer: %d {\n\t\t\tVersion: 100" % t)
        if t == 0:
            w("\t\t\tLayerElement:  {\n\t\t\t\tType: \"LayerElementNormal\"\n\t\t\t\tTypedIndex: 0\n\t\t\t}")
            w("\t\t\tLayerElement:  {\n\t\t\t\tType: \"LayerElementMaterial\"\n\t\t\t\tTypedIndex: 0\n\t\t\t}")
            if colors:
                w("\t\t\tLayerElement:  {\n\t\t\t\tType: \"LayerElementColor\"\n\t\t\t\tTypedIndex: 0\n\t\t\t}")
        if t < len(uvs):
            w("\t\t\tLayerElement:  {\n\t\t\t\tType: \"LayerElementUV\"\n\t\t\t\tTypedIndex: %d\n\t\t\t}" % t)
        w("\t\t}")
    w("\t}")
    w("\tModel: 2000, \"Model::Mesh\", \"Mesh\" {\n\t\tVersion: 232\n\t\tProperties70:  {\n\t\t}\n\t\tShading: T\n\t\tCulling: \"CullingOff\"\n\t}")
    for i, n in enumerate(names):
        w("\tMaterial: %d, \"Material::%s\", \"\" {\n\t\tVersion: 102\n\t\tShadingModel: \"phong\"\n\t\tMultiLayer: 0\n\t\tProperties70:  {\n\t\t}\n\t}" % (3000 + i, n))
    w("}")
    w("Connections:  {")
    w("\tC: \"OO\",2000,0")
    w("\tC: \"OO\",1000,2000")
    for i in range(nslots):
        w("\tC: \"OO\",%d,2000" % (3000 + i))
    w("}")
    return "\n".join(L) + "\n"


def main():
    a = sys.argv[1:]
    if a[0] == "--all":
        root, out_root, plan_path = a[1:4]
        plan = json.load(open(plan_path))
        for m in plan["meshes"]:
            geo = json.load(open(m["file"]))
            names = [s["slot"] for s in m["slots"]]
            lods = geo["lods"][:1] if m.get("kit_nanite") else geo["lods"]
            for li, lod in enumerate(lods):
                rel = m["path"][len("/Game/"):]
                out = os.path.join(out_root, rel + ("_LOD%d" % li if li else "") + ".fbx")
                os.makedirs(os.path.dirname(out), exist_ok=True)
                open(out, "w").write(fbx_for(lod, names))
            print("ok", m["path"], len(lods))
        return
    src, out = a[0], a[1]
    lod = int(a[a.index("--lod") + 1]) if "--lod" in a else 0
    names = a[a.index("--slots") + 1].split(",") if "--slots" in a else []
    open(out, "w").write(fbx_for(json.load(open(src))["lods"][lod], names))


main()
