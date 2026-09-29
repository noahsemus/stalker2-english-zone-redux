# Remove the dev test pak(s) so only the Vortex-installed release copy (_20_P) is left.
$game = "C:\Program Files (x86)\Steam\steamapps\common\S.T.A.L.K.E.R. 2 Heart of Chornobyl\Stalker2"
if (Get-Process -Name "Stalker2-Win64-Shipping" -ErrorAction SilentlyContinue) { throw "game is running" }
Get-ChildItem "$game\Content\Paks\~mods" -Directory -Filter "zzz_EnglishZoneRedux*_PakTest" | Remove-Item -Recurse -Force
