r"""Zone Kit editor script: build the English Zone Redux override assets from work/plan.json.
All content is from rbwadle's English Zone (https://www.nexusmods.com/stalker2heartofchornobyl/mods/1559).

Runs headless (editor closed) or in the live editor via ue_exec.py. For each planned asset it duplicates the
game asset to /<DEST>/<same path> (the Zone Kit override location), then
  textures : re-imports the decoded English image (B8G8R8A8 DDS) keeping every texture setting, and
             adjusts LOD bias so the in-game size matches what the old mod shipped;
  materials: applies the old mod's changed parameters;
  meshes   : rebuilds the geometry (Nanite leaf level / render LODs decoded from the old mod) and sets the
             old mod's material slots.
Environment: EZU_DEST (default /EnglishZoneRedux), EZU_KINDS (textures,materials,meshes),
EZU_ONLY (substring filter), EZU_FORCE=1 (rebuild existing), EZU_LOG (log file).
"""
import unreal, json, os, math, time, traceback

ROOT = r"C:/Users/noahs/OneDrive/Documents/GitHub/stalker2-english-zone-redux/work"
DEST = os.environ.get("EZU_DEST", "/EnglishZoneRedux")
KINDS = os.environ.get("EZU_KINDS", "textures,materials,meshes").split(",")
ONLY = os.environ.get("EZU_ONLY", "")
FORCE = os.environ.get("EZU_FORCE", "0") == "1"
LOG = os.environ.get("EZU_LOG", ROOT + "/build_mod.log")
EAL = unreal.EditorAssetLibrary
AT = unreal.AssetToolsHelpers.get_asset_tools()
lines = []


def log(s):
    lines.append(str(s)); unreal.log("[EZU] " + str(s))
    open(LOG, "w", encoding="utf-8").write("\n".join(lines))


def dst_of(game_path):
    return DEST + game_path[len("/Game"):]


def duplicate(src, dst):
    if EAL.does_asset_exist(dst):
        return unreal.load_asset(dst), False
    r = EAL.duplicate_asset(src, dst)
    if r is None:
        folder, name = dst.rsplit("/", 1)
        r = AT.duplicate_asset(name, folder, unreal.load_asset(src))
    if r is None:
        raise RuntimeError("duplicate failed: %s" % src)
    return r, True


def build_texture(t):
    dst = dst_of(t["path"])
    if EAL.does_asset_exist(dst) and not FORCE:
        return "exists"
    tex, _ = duplicate(t["path"], dst)
    folder, name = dst.rsplit("/", 1)
    task = unreal.AssetImportTask()
    task.filename = t["file"]
    task.destination_path = folder
    task.destination_name = name
    task.replace_existing = True
    task.replace_existing_settings = False
    task.automated = True
    task.save = False
    task.factory = unreal.TextureFactory()
    AT.import_asset_tasks([task])
    if not list(task.get_editor_property("imported_object_paths")):
        raise RuntimeError("import failed")
    tex = unreal.load_asset(dst)
    tw, th = t["target"]
    bias = tex.get_editor_property("lod_bias")
    for _ in range(4):                                  # match the in-game size the old mod had
        w = tex.blueprint_get_size_x()
        if w == tw or w == 0:
            break
        step = int(round(math.log2(w / tw)))
        if step == 0:
            break
        bias += step
        tex.set_editor_property("lod_bias", bias)
    EAL.save_loaded_asset(tex, False)
    return "size %dx%d bias %d" % (tex.blueprint_get_size_x(), tex.blueprint_get_size_y(), bias)


def build_material(m):
    dst = dst_of(m["path"])
    mi, _ = duplicate(m["path"], dst)
    for k, v in m["scalars"].items():
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi, k, v)
    for k, v in m["vectors"].items():
        unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(*v))
    unreal.MaterialEditingLibrary.update_material_instance(mi)
    EAL.save_loaded_asset(mi, False)
    return "%d scalars, %d vectors" % (len(m["scalars"]), len(m["vectors"]))


FBX_ROOT = ROOT + "/fbx"


def fbx_task(fbx, folder, name):
    ui = unreal.FbxImportUI()
    ui.set_editor_property("import_mesh", True)
    ui.set_editor_property("import_as_skeletal", False)
    ui.set_editor_property("import_materials", False)
    ui.set_editor_property("import_textures", False)
    ui.set_editor_property("import_animations", False)
    ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_STATIC_MESH)
    d = ui.get_editor_property("static_mesh_import_data")
    d.set_editor_property("combine_meshes", True)
    d.set_editor_property("auto_generate_collision", False)
    d.set_editor_property("normal_import_method", unreal.FBXNormalImportMethod.FBXNIM_IMPORT_NORMALS)
    d.set_editor_property("reorder_material_to_fbx_order", True)
    d.set_editor_property("remove_degenerates", True)
    d.set_editor_property("convert_scene", True)
    d.set_editor_property("force_front_x_axis", False)
    d.set_editor_property("vertex_color_import_option", unreal.VertexColorImportOption.REPLACE)
    task = unreal.AssetImportTask()
    task.filename = fbx
    task.destination_path = folder
    task.destination_name = name
    task.replace_existing = True
    task.replace_existing_settings = False
    task.automated = True
    task.save = False
    task.factory = unreal.FbxFactory()
    task.options = ui
    return task


def build_mesh(m):
    dst = dst_of(m["path"])
    if EAL.does_asset_exist(dst) and not FORCE:
        return "exists"
    sm, _ = duplicate(m["path"], dst)
    nanite_before = sm.get_editor_property("nanite_settings").get_editor_property("enabled")
    folder, name = dst.rsplit("/", 1)
    rel = m["path"][len("/Game/"):]
    task = fbx_task(FBX_ROOT + "/" + rel + ".fbx", folder, name)
    AT.import_asset_tasks([task])
    info = []
    if not list(task.get_editor_property("imported_object_paths")):
        raise RuntimeError("fbx import produced nothing")
    sm = unreal.load_asset(dst)
    lod = 1
    while os.path.exists(FBX_ROOT + "/" + rel + "_LOD%d.fbx" % lod):
        r = unreal.EditorStaticMeshLibrary.import_lod(sm, lod, FBX_ROOT + "/" + rel + "_LOD%d.fbx" % lod)
        info.append("lod%d import -> %s" % (lod, r))
        lod += 1
    mats = []
    for s in m["slots"]:
        mat = unreal.load_asset(s["material"]) if s["material"] else None
        mats.append(unreal.StaticMaterial(material_interface=mat, material_slot_name=s["slot"]))
    sm.set_editor_property("static_materials", mats)
    ns = sm.get_editor_property("nanite_settings")
    if ns.get_editor_property("enabled") != nanite_before:
        ns.set_editor_property("enabled", nanite_before)
        sm.set_editor_property("nanite_settings", ns)
        info.append("nanite restored")
    EAL.save_loaded_asset(sm, False)
    info.insert(0, "lods %d, lod0 verts %d, slots %d, nanite %s" % (sm.get_num_lods(),
        unreal.EditorStaticMeshLibrary.get_number_verts(sm, 0), len(mats), nanite_before))
    return "; ".join(info)


def main():
    plan = json.load(open(ROOT + "/plan.json"))
    log("dest=%s kinds=%s only=%r force=%s" % (DEST, KINDS, ONLY, FORCE))
    t0 = time.time()
    for kind, fn in (("textures", build_texture), ("materials", build_material), ("meshes", build_mesh)):
        if kind not in KINDS:
            continue
        ok = bad = 0
        for item in plan[kind]:
            if ONLY and ONLY not in item["path"]:
                continue
            try:
                r = fn(item)
                log("OK   %s %s" % (item["path"], r)); ok += 1
            except Exception:
                log("FAIL %s %s" % (item["path"], traceback.format_exc().strip().splitlines()[-1])); bad += 1
        log("%s: %d ok, %d failed (%.0fs)" % (kind, ok, bad, time.time() - t0))
    log("DONE")


main()
