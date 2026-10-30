param([string]$Python='python')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent $MyInvocation.MyCommand.Path))
Set-Location -LiteralPath $projectRoot
& $Python -m PyInstaller --clean --noconfirm --distpath dist-rylume --workpath build-rylume Rylume.spec
if($LASTEXITCODE -ne 0){throw 'Rylume build failed'}
$numpyLibs=Join-Path $projectRoot 'dist-rylume\Rylume\_internal\numpy.libs'
if(Test-Path -LiteralPath $numpyLibs){Get-ChildItem -LiteralPath $numpyLibs -Filter '*.dll' | Copy-Item -Destination (Join-Path $projectRoot 'dist-rylume\Rylume\_internal') -Force}
$releasePath=Join-Path $projectRoot 'dist-rylume\Rylume'
foreach($notice in @('LICENSE','COPYRIGHT','THIRD_PARTY_NOTICES.md')){Copy-Item -LiteralPath (Join-Path $projectRoot $notice) -Destination $releasePath -Force}
Copy-Item -LiteralPath (Join-Path $projectRoot 'licenses') -Destination $releasePath -Recurse -Force
Get-ChildItem -LiteralPath (Join-Path $projectRoot 'packaging') -File | Copy-Item -Destination $releasePath -Force
Write-Output (Join-Path $projectRoot 'dist-rylume\Rylume\Rylume.exe')
