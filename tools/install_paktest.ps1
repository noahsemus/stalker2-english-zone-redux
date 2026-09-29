# Install a mod's Zone Kit OverrideContent build as a dev test pak.
# Usage:  powershell -File install_paktest.ps1 [-Mod EnglishZoneRedux]
# Run only while the game is closed. Revert with revert_paktest.ps1.
param([string]$Mod = "EnglishZoneRedux")
$kit  = "G:\Epic Games\STALKER2ZoneKit"
$game = "C:\Program Files (x86)\Steam\steamapps\common\S.T.A.L.K.E.R. 2 Heart of Chornobyl\Stalker2"
$src  = "$kit\Stalker2\SavedMods\Staged\$Mod\Windows\OverrideContent\Windows\Stalker2\Mods\$Mod\Content\Paks\Windows"
$dst  = "$game\Content\Paks\~mods\zzz_${Mod}_PakTest"
if (Get-Process -Name "Stalker2-Win64-Shipping" -ErrorAction SilentlyContinue) { throw "game is running" }
New-Item -ItemType Directory -Force $dst | Out-Null
# "_30_P" = mount order 3103: the dev test copy beats other mods AND the Vortex-installed release copy
# (zzz_<Mod>_20_P, order 2103). Release zips keep the _20_P name. The three IoStore files share a base name.
Remove-Item "$dst\*" -Force -ErrorAction SilentlyContinue
foreach ($ext in "pak","ucas","utoc") { Copy-Item "$src\${Mod}Stalker2-Windows-OverrideContent.$ext" "$dst\zzz_${Mod}_30_P.$ext" -Force }
# NewContent (mod-only assets under /<Mod>/, e.g. the ModKit subsystem) keeps the kit's file name: its package
# paths exist nowhere else, so mount order doesn't matter, and it matches how other Zone Kit mods ship it.
$newSrc = "$kit\Stalker2\SavedMods\Staged\$Mod\Windows\NewContent\Windows\Stalker2\Mods\$Mod\Content\Paks\Windows"
if (Test-Path "$newSrc\${Mod}Stalker2-Windows-NewContent.utoc") {
    foreach ($ext in "pak","ucas","utoc") { Copy-Item "$newSrc\${Mod}Stalker2-Windows-NewContent.$ext" "$dst\${Mod}Stalker2-Windows-NewContent.$ext" -Force }
}
Get-ChildItem $dst | Select-Object Name, Length, LastWriteTime
