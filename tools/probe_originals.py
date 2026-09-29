# Headless: dump the kit's original assets that rbwadle's English Zone (Nexus 1559) overrode (textures, meshes, materials)
# plus the Python mesh-description API surface. Output JSON to work/originals.json.
import unreal, json, os
ROOT = r"C:/Users/noahs/OneDrive/Documents/GitHub/stalker2-english-zone-redux/work"
imports = json.load(open(os.path.join(ROOT, "mod_imports.json")))
out = {"textures": {}, "meshes": {}, "materials": {}, "api": {}}

def s(v):
    return str(v)

for pkg in sorted(imports):
    if not pkg.startswith("/Game/"):
        continue
    name = pkg.rsplit("/", 1)[1]
    if not unreal.EditorAssetLibrary.does_asset_exist(pkg):
        out.setdefault("missing", []).append(pkg); continue
    a = unreal.load_asset(pkg)
    if isinstance(a, unreal.Texture2D):
        d = {}
        for p in ["compression_settings", "lod_group", "srgb", "virtual_texture_streaming", "lod_bias", "max_texture_size", "mip_gen_settings", "never_stream"]:
            try: d[p] = s(a.get_editor_property(p))
            except Exception: d[p] = None
        d["size"] = [a.blueprint_get_size_x(), a.blueprint_get_size_y()]
        out["textures"][pkg] = d
    elif isinstance(a, unreal.StaticMesh):
        d = {"slots": []}
        for m in a.get_editor_property("static_materials"):
            mi = m.get_editor_property("material_interface")
            d["slots"].append([s(m.get_editor_property("material_slot_name")), mi.get_path_name() if mi else None])
        d["lods"] = a.get_num_lods()
        try:
            ns = a.get_editor_property("nanite_settings")
            d["nanite"] = bool(ns.get_editor_property("enabled"))
        except Exception as e:
            d["nanite"] = "?" + str(e)
        try:
            d["tris_lod0"] = unreal.EditorStaticMeshLibrary.get_number_verts(a, 0)
        except Exception: pass
        out["meshes"][pkg] = d
    elif isinstance(a, unreal.MaterialInstanceConstant):
        d = {"parent": a.get_editor_property("parent").get_path_name() if a.get_editor_property("parent") else None}
        d["scalars"] = {s(p.get_editor_property("parameter_info").get_editor_property("name")): p.get_editor_property("parameter_value") for p in a.get_editor_property("scalar_parameter_values")}
        d["vectors"] = {s(p.get_editor_property("parameter_info").get_editor_property("name")): s(p.get_editor_property("parameter_value")) for p in a.get_editor_property("vector_parameter_values")}
        d["textures"] = {s(p.get_editor_property("parameter_info").get_editor_property("name")): (p.get_editor_property("parameter_value").get_path_name() if p.get_editor_property("parameter_value") else None) for p in a.get_editor_property("texture_parameter_values")}
        out["materials"][pkg] = d
    else:
        out.setdefault("other", {})[pkg] = a.get_class().get_name()

for cls in ["StaticMeshDescription", "MeshDescriptionBase", "StaticMesh", "EditorStaticMeshLibrary", "StaticMeshEditorSubsystem"]:
    c = getattr(unreal, cls, None)
    out["api"][cls] = [m for m in dir(c) if not m.startswith("_")] if c else None
out["api"]["interchange_gltf"] = [n for n in dir(unreal) if "GLTF" in n.upper()][:40]
out["api"]["fbx"] = [n for n in dir(unreal) if n.startswith("Fbx")][:40]
json.dump(out, open(os.path.join(ROOT, "originals.json"), "w"), indent=1)
unreal.log("[EZP] done")
