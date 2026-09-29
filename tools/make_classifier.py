r"""Write the cook's package classifier lists from plan.json (every rebuilt asset is an override).

    python make_classifier.py
Writes tools/classifier/EnglishZoneRedux/{OverridePackages,NewPackages}.txt and copies them to the kit.
"""
import json, os, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
MOD = "EnglishZoneRedux"
KIT = r"G:/Epic Games/STALKER2ZoneKit/Stalker2/SavedMods/PackageClassifier/" + MOD
plan = json.load(open(os.path.join(HERE, "..", "work", "plan.json")))
over = sorted("/%s%s" % (MOD, x["path"][len("/Game"):]) for k in ("textures", "materials", "meshes") for x in plan[k])
out = os.path.join(HERE, "classifier", MOD)
os.makedirs(out, exist_ok=True)
open(os.path.join(out, "OverridePackages.txt"), "w", newline="\n").write("\n".join(over) + "\n")
open(os.path.join(out, "NewPackages.txt"), "w", newline="\n").write("/%s/%s\n" % (MOD, MOD))
os.makedirs(KIT, exist_ok=True)
for f in ("OverridePackages.txt", "NewPackages.txt"):
    shutil.copy(os.path.join(out, f), os.path.join(KIT, f))
print(len(over), "override packages")
