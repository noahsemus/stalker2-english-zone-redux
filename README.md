# English Zone Redux

In-world Ukrainian signs, graffiti, posters, shop signs and markers shown in English in
S.T.A.L.K.E.R. 2: Heart of Chornobyl, for the current game version (2.0).

This is a port of rbwadle's **English Zone** (Nexus mod 1559, v1.10, Oct 2025). That mod was built for the
1.x engine (UE 5.1) and silently stopped loading when the game moved to UE 5.5. All translated artwork is
the original author's work; this project only decodes it from the old paks and rebuilds it for the current
engine with the STALKER 2 Zone Kit. No original assets are stored in this repository.

## Install
Copy the pak files into `Stalker2\Content\Paks\~mods\` and remove the old English Zone.

## Building
See [BUILD.md](BUILD.md). The tools decode UE 5.1 cooked textures (including streaming virtual textures),
Nanite meshes and material instances without property mappings, then drive the Zone Kit editor to rebuild
and cook them.
