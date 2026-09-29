# English Zone Redux

**All credit goes to rbwadle, the creator of [English Zone](https://www.nexusmods.com/stalker2heartofchornobyl/mods/1559).**
Every translated sign, poster, graffiti, stencil and remodelled 3D lettering in this mod is rbwadle's work.
Please visit and endorse the original: https://www.nexusmods.com/stalker2heartofchornobyl/mods/1559

English Zone replaces the Ukrainian text in S.T.A.L.K.E.R. 2: Heart of Chornobyl's world (signs, shop fronts,
posters, graffiti, markers) with English versions. Its last release (v1.10, October 2025) was built for the
game's 1.x engine (UE 5.1) and stopped loading when the game moved to UE 5.5 in version 2.0.

English Zone Redux is only a compatibility port: nothing was re-drawn or re-translated. The tools in this
repository read rbwadle's original cooked files and rebuild the same assets with the STALKER 2 Zone Kit so
they load in the current game. None of the original assets are stored in this repository; building requires
the original mod from its Nexus page.

If rbwadle updates English Zone or asks for this port to be taken down, that takes precedence.

## Install
Copy the pak files into `Stalker2\Content\Paks\~mods\` and remove the old English Zone.

## Building
See [BUILD.md](BUILD.md). The tools decode UE 5.1 cooked textures (including streaming virtual textures),
Nanite meshes and material instances without property mappings, then drive the Zone Kit editor to rebuild
and cook them.

## Credits
- **rbwadle** — English Zone: all translations, textures and sign models ([Nexus](https://www.nexusmods.com/stalker2heartofchornobyl/mods/1559)).
- noahsemus — port to game 2.0.
- BC7 partition tables transcribed from Microsoft DirectXTex (MIT License).
