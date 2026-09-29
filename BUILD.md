# English Zone Redux — how it is built

Port of rbwadle's [English Zone](https://www.nexusmods.com/stalker2heartofchornobyl/mods/1559) (v1.10,
Oct 2025) to the current game (2.0, UE 5.5.4). All translated content is rbwadle's; this document only
covers how it is carried over. Input: the original mod's paks, downloaded from its Nexus page.
The original was cooked for the 1.x game (UE 5.1, IoStore TOC v5); the current game only loads v8
containers, so the mod silently stopped working. Nothing is re-authored here: every translated
texture, sign mesh and material change is decoded from the old paks and rebuilt in the Zone Kit.

## Pipeline (all tools in `tools/`, Python = the kit's embedded 3.11)

| Step | Tool | Output (`work/`, not committed) |
|---|---|---|
| Unpack old container | `UnrealPak <old>.utoc -Extract work/extracted` | cooked 5.1 packages |
| Resolve imports | `mod_imports.py` (+ `zen51.py`: CityHash64 package ids, zen header, container header) | `mod_imports.json`, `package_ids.json` |
| Textures | `export_textures.py` (regular mips + streaming virtual textures, tiles reassembled) → `bcdec` (Rust: BC1/4/5/7 → BGRA DDS; the kit rejects compressed DDS) | `dds/`, `rgba/`, `textures.tsv` |
| Meshes | `export_meshes.py` (`nanite51.py`: full-detail Nanite leaf clusters; `sm51.py`: non-Nanite render LODs) → `write_fbx.py` (ASCII FBX, Y mirrored for the importer, winding verified against the game mesh) | `meshes/*.json`, `fbx/` |
| Material slots | `mesh_slots.py` (FStaticMaterial from unversioned data; null = reference to another overridden asset) | `mesh_slots.json` |
| Material params | `mi_params.py` | `mi_params.json` |
| Originals | `probe_originals.py` (headless) | `originals.json` |
| Plan | `make_plan.py` | `plan.json` |
| Build in editor | `run_build.py [kinds] [filter] [force]` → `build_mod.py` in the open editor (remote Python) | assets in `<kit>\Stalker2\Mods\EnglishZoneRedux\Content` |
| Cook + install | `cook_and_install.ps1` | `~mods\zzz_EnglishZoneRedux_PakTest\` |

## Findings
- 381 of 399 textures are streaming virtual textures (RawGPU tiles, 128 px + 4 px border, Morton order).
  Cooked sizes are one mip below the source for many of them; `build_mod.py` adjusts LOD bias so the
  in-game size matches the old mod.
- 61 of 64 meshes are Nanite; their stored fallback LOD is heavily reduced, so the geometry comes from
  the Nanite pages (5.1 encoding: strip indices, per-page vertex refs, parent-page refs). Leaf triangle
  counts equal `NumInputTriangles` for all 61.
- Skipped as unchanged: `T_sign_font_02_MAH` (byte-identical), `MI_sign_books_01`, `MI_sign_firefly_01`
  (same parameters). The 7 new `MI_sign_font_02_a_*` instances were referenced by nothing; skipped.
  `MI_sign_font_02_a`: HUE_G_Color / HUE_B_Color set to white.
- The old "TranslateLens" subtitle actor was never spawned by anything; not ported.
- Vertex colours (2 meshes) go through the FBX (LayerElementColor, import option Replace).
- The FBX importer drops zero-area triangles present in the old meshes (1-10% on the NII markers and a few signs, e.g. SM_uni_nii_mark_01_a_02: 912 collapsed + 780 near-zero-area). Checked; nothing visible is lost.
