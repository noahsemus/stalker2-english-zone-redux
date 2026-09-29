r"""Build work/plan.json: everything build_mod.py (editor side) needs, from the offline extraction results.

    python make_plan.py
Inputs (work/): textures.tsv, rgba/, meshes/, mesh_slots.json, mi_params.json, originals.json, package_ids.json
"""
import json, os

WORK = os.path.join(os.path.dirname(__file__), "..", "work")
W = lambda *p: os.path.abspath(os.path.join(WORK, *p)).replace("\\", "/")

# Assets the old mod overrode without changing them (verified against the kit originals): skipped.
UNCHANGED = {
    "/Game/_Stalker_2/props/sign/Textures/T_sign_font_02_MAH",       # byte-identical to the game's
    "/Game/_Stalker_2/props/sign/Materials/MI_sign_books_01",        # same parameters as the game's
    "/Game/_Stalker_2/props/sign/Materials/MI_sign_firefly_01",
}


def game_path(rel):                     # "Stalker2/Content/x/y" -> "/Game/x/y"
    return "/Game/" + rel[len("Stalker2/Content/"):]


def main():
    ids = json.load(open(W("package_ids.json")))
    by_name = {}
    for n in ids.values():
        if n.startswith("/Game/"):
            by_name.setdefault(n.rsplit("/", 1)[1], []).append(n)
    originals = json.load(open(W("originals.json")))
    plan = {"textures": [], "materials": [], "meshes": []}

    for line in open(W("textures.tsv"), encoding="utf-8").read().splitlines()[1:]:
        rel, fmt, kind, size, exported, status = line.split("\t")
        gp = game_path(rel)
        if gp in UNCHANGED or status != "ok":
            continue
        w, h = (int(x) for x in exported.split("x"))
        plan["textures"].append(dict(path=gp, file=W("rgba", rel + ".dds"), target=[w, h], format=fmt))

    mi = json.load(open(W("mi_params.json")))
    for gp, orig in originals["materials"].items():
        if gp in UNCHANGED:
            continue
        mod = mi[gp]
        scal = {k: v for k, v in mod["scalar"].items() if abs(orig["scalars"].get(k, 1e9) - v) > 1e-4}
        vec = {}
        for k, v in mod.get("vector", {}).items():
            o = orig["vectors"].get(k)
            ov = [float(x.split(":")[1]) for x in o.split("{")[1].rstrip("}>").split(",")] if o else None
            if ov is None or max(abs(a - b) for a, b in zip(ov, v)) > 1e-3:
                vec[k] = v
        plan["materials"].append(dict(path=gp, scalars=scal, vectors=vec))

    slots = json.load(open(W("mesh_slots.json")))
    changed_materials = {m["path"] for m in plan["materials"]}
    for gp, sl in slots.items():
        rel = "Stalker2/Content/" + gp[len("/Game/"):]
        geo = W("meshes", rel + ".json")
        resolved = []
        for s in sl:
            mat = s["material"]
            if mat is None:
                cands = by_name.get(s["imported"]) or by_name.get(s["slot"]) or []
                cands = sorted(cands, key=lambda c: (c not in changed_materials, len(c)))
                mat = cands[0] if cands else None
            resolved.append(dict(slot=s["slot"], imported=s["imported"], material=mat))
        orig = originals["meshes"].get(gp, {})
        plan["meshes"].append(dict(path=gp, file=geo, slots=resolved, kit_nanite=orig.get("nanite"),
                                   kit_lods=orig.get("lods")))

    json.dump(plan, open(W("plan.json"), "w"), indent=1)
    print(len(plan["textures"]), "textures,", len(plan["materials"]), "materials,", len(plan["meshes"]), "meshes")
    for m in plan["materials"]:
        print("MI", m["path"].rsplit("/", 1)[1], m["scalars"], m["vectors"])
    for m in plan["meshes"]:
        bad = [s for s in m["slots"] if not s["material"]]
        if bad:
            print("UNRESOLVED", m["path"], bad)


main()
