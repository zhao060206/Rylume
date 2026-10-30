param([string]$BuildDirectory='')
$ErrorActionPreference='Stop'
$projectRoot=[IO.Path]::GetFullPath((Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)))
$buildPath=if($BuildDirectory){[IO.Path]::GetFullPath($BuildDirectory)}else{Join-Path $projectRoot 'dist-rylume\Rylume'}
if(-not(Test-Path -LiteralPath (Join-Path $buildPath 'Rylume.exe'))){throw 'Rylume.exe missing'}
$desktopPath=[Environment]::GetFolderPath('Desktop')
$targetPath=[IO.Path]::GetFullPath((Join-Path $desktopPath 'Rylume'))
if($targetPath -ne [IO.Path]::GetFullPath((Join-Path $desktopPath 'Rylume'))){throw 'Unexpected installation directory'}
if(Get-Process Rylume -ErrorAction SilentlyContinue | Where-Object {$_.Path -eq (Join-Path $targetPath 'Rylume.exe')}){throw 'Rylume is open; its files and active work were preserved'}
New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
Get-ChildItem -LiteralPath $buildPath | Copy-Item -Destination $targetPath -Recurse -Force
@'
理象 · Rylume 3.0
双击 Rylume.exe 或桌面“理象 Rylume”快捷方式。
历史任务与配置继续使用原数据目录 %LOCALAPPDATA%\CellFigureStudio。
旧安装与数据保留；没有复制或迁移出第二份科研数据。
本版改进画布操作、草稿恢复、版本历史、素材检索、批注对比及导出提示，场景和导出保持兼容。
'@ | Set-Content -LiteralPath (Join-Path $targetPath 'README.txt') -Encoding utf8
$shell=New-Object -ComObject WScript.Shell
$link=$shell.CreateShortcut((Join-Path $desktopPath '理象 Rylume.lnk'))
$link.TargetPath=Join-Path $targetPath 'Rylume.exe'
$link.Arguments='--port 8779 --no-migrate'
$link.WorkingDirectory=$targetPath
$link.IconLocation=$link.TargetPath
$link.Description='理象 Rylume · 科研图形工作台'
$link.Save()
Write-Output $targetPath
