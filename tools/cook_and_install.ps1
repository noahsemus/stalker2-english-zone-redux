# Cook a Zone Kit mod of this project and install the override pak into the game as a dev test pak.
# Usage:  powershell -File cook_and_install.ps1 [-Mod EnglishZoneRedux]
# Save your assets in the Zone Kit editor first. Takes 5-6 minutes.
param([string]$Mod = "EnglishZoneRedux")
$kit = "G:\Epic Games\STALKER2ZoneKit"
$log = "$env:TEMP\${Mod}_cook.log"
Write-Host "Cooking $Mod (log: $log) ..."
& "$kit\Engine\Build\BatchFiles\RunUAT.bat" GSCCookMod "-Project=$kit\Stalker2\Stalker2.uproject" "-PluginPath=$kit\Stalker2\Mods\$Mod\$Mod.uplugin" "-PackageClassifierOutputDir=$kit\Stalker2\SavedMods\PackageClassifier\$Mod" "-UnrealExe=$kit\Stalker2\Binaries\Win64\Stalker2ModEditor-Win64-Shipping-Cmd.exe" -TargetPlatform=Win64 -nocompile -nocompileuat *> $log
if ($LASTEXITCODE -ne 0) { Write-Host "COOK FAILED (exit $LASTEXITCODE). See $log"; exit 1 }
Write-Host "Cook OK."
while (Get-Process -Name "Stalker2-Win64-Shipping" -ErrorAction SilentlyContinue) { Write-Host "Game is running - close it to install..."; Start-Sleep -Seconds 10 }
& "$PSScriptRoot\install_paktest.ps1" -Mod $Mod | Out-Null
Write-Host "Installed:"
Get-ChildItem "C:\Program Files (x86)\Steam\steamapps\common\S.T.A.L.K.E.R. 2 Heart of Chornobyl\Stalker2\Content\Paks\~mods\zzz_${Mod}_PakTest" | Select-Object Name, Length, LastWriteTime
