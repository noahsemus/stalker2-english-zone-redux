r"""Run build_mod.py inside the open Zone Kit editor (remote Python execution).

    python run_build.py [kinds] [only] [force]
e.g.  python run_build.py meshes SM_sign_pharmacy_01 1
"""
import sys, subprocess
kinds = sys.argv[1] if len(sys.argv) > 1 else "textures,materials,meshes"
only = sys.argv[2] if len(sys.argv) > 2 else ""
force = sys.argv[3] if len(sys.argv) > 3 else "0"
script = r"C:/Users/noahs/OneDrive/Documents/GitHub/stalker2-english-zone-redux/tools/build_mod.py"
code = ("import os\nos.environ['EZU_KINDS']=%r\nos.environ['EZU_ONLY']=%r\nos.environ['EZU_FORCE']=%r\n"
        "os.environ['EZU_DEST']='/EnglishZoneRedux'\nexec(open(%r, encoding='utf-8').read(), {'__name__': '__main__'})\n"
        % (kinds, only, force, script))
ue_exec = r"C:/Users/noahs/OneDrive/Documents/GitHub/stalker2-english-zone-redux/tools/ue_exec.py"
open(r"C:/Users/noahs/OneDrive/Documents/GitHub/stalker2-english-zone-redux/work/_run.py", "w").write(code)
sys.exit(subprocess.call([sys.executable, ue_exec, r"C:/Users/noahs/OneDrive/Documents/GitHub/stalker2-english-zone-redux/work/_run.py"]))
