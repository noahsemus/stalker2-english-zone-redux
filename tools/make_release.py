r"""Package a release zip from the Zone Kit's staged cook output.

    python make_release.py <version>          e.g. python make_release.py 0.1
Writes work/release/EnglishZoneRedux-v<version>.zip containing README.txt and
  zzz_EnglishZoneRedux_20_P.{pak,ucas,utoc}             (override container, renamed for mount order)
  EnglishZoneReduxStalker2-Windows-NewContent.{pak,ucas,utoc}
"""
import os, sys, zipfile

MOD = "EnglishZoneRedux"
STAGED = r"G:/Epic Games/STALKER2ZoneKit/Stalker2/SavedMods/Staged/%s/Windows" % MOD
SUB = "Windows/Stalker2/Mods/%s/Content/Paks/Windows" % MOD
HERE = os.path.dirname(os.path.abspath(__file__))

README = """English Zone Redux v{v}
=======================

ALL CREDIT GOES TO rbwadle, the creator of English Zone:
https://www.nexusmods.com/stalker2heartofchornobyl/mods/1559
Every translated sign, poster, graffiti, stencil and 3D sign lettering in this mod is rbwadle's work.
Please visit, endorse and support the original.

English Zone's last release (v1.10) was built for the game's 1.x engine and no longer loads in
S.T.A.L.K.E.R. 2 version 2.0. English Zone Redux is only a compatibility port of that content:
nothing was re-drawn or re-translated. If rbwadle releases an update or asks for this port to be
removed, that takes precedence.

Install
-------
1. Remove the old English Zone (it does nothing on 2.0 anyway).
2. Copy all six files from this zip into
   S.T.A.L.K.E.R. 2 Heart of Chornobyl\\Stalker2\\Content\\Paks\\~mods\\
   (a subfolder inside ~mods is fine).

Uninstall: delete those six files.

Source and build tools: https://github.com/noahsemus/stalker2-english-zone-redux
"""


def main():
    v = sys.argv[1]
    out_dir = os.path.join(HERE, "..", "work", "release")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "%s-v%s.zip" % (MOD, v))
    files = []
    for ext in ("pak", "ucas", "utoc"):
        files.append((os.path.join(STAGED, "OverrideContent", SUB, "%sStalker2-Windows-OverrideContent.%s" % (MOD, ext)),
                      "zzz_%s_20_P.%s" % (MOD, ext)))
        files.append((os.path.join(STAGED, "NewContent", SUB, "%sStalker2-Windows-NewContent.%s" % (MOD, ext)),
                      "%sStalker2-Windows-NewContent.%s" % (MOD, ext)))
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr("README.txt", README.format(v=v).replace("\n", "\r\n"))
        for src, name in files:
            z.write(src, name)
    print(out, os.path.getsize(out))


main()
