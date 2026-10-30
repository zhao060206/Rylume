param([Parameter(Mandatory=$true)][string]$PlanPath)
$ErrorActionPreference='Stop'
$planFile=[IO.Path]::GetFullPath($PlanPath)
$plan=Get-Content -LiteralPath $planFile -Raw -Encoding UTF8 | ConvertFrom-Json
function Absolute([string]$p){[IO.Path]::GetFullPath($p).TrimEnd([IO.Path]::DirectorySeparatorChar)}
function Within([string]$p,[string]$root){$p.Equals($root,[StringComparison]::OrdinalIgnoreCase) -or $p.StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)}
$target=Absolute $plan.install_dir; $data=Absolute $plan.data_dir; $stage=Absolute $plan.staged_dir
$backup=Absolute $plan.backup_dir; $next=Absolute $plan.new_dir
$parent=Split-Path -Parent $target
if($plan.schema_version -ne 1 -or $plan.nonce -notmatch '^[a-f0-9]{32}$'){throw 'Invalid update plan'}
if((Within $target (Absolute $env:WINDIR)) -or (Within $target $data) -or (Within $data $target) -or $target -eq [IO.Path]::GetPathRoot($target).TrimEnd('\')){throw 'Unsafe installation target'}
if((Split-Path -Parent $backup) -ne $parent -or (Split-Path -Parent $next) -ne $parent -or $backup -ne ($target+'.previous-'+$plan.nonce) -or $next -ne ($target+'.next-'+$plan.nonce)){throw 'Invalid backup target'}
if(-not (Within $stage ($data+'\updates\staged')) -or -not (Within $planFile ($data+'\updates\apply'))){throw 'Invalid staging target'}
if(-not (Test-Path -LiteralPath ($stage+'\Rylume.exe')) -or -not (Test-Path -LiteralPath ($target+'\Rylume.exe'))){throw 'Incomplete application'}
if((Absolute $plan.health_file) -ne ((Split-Path -Parent $planFile)+'\healthy.json')){throw 'Invalid health path'}
function Log([string]$message){('[{0}] {1}' -f (Get-Date -Format o),$message) | Add-Content -LiteralPath $plan.log_file -Encoding UTF8}
function QuoteArg([string]$value){'"'+($value -replace '(\\*)"','$1$1\"' -replace '(\\+)$','$1$1')+'"'}
function Launch([string]$folder,[bool]$health){
    $arguments=@($plan.args)
    if($health){$arguments+=@('--update-plan',$planFile,'--update-nonce',$plan.nonce)}
    $quoted=($arguments | ForEach-Object {QuoteArg ([string]$_)}) -join ' '
    Start-Process -FilePath ($folder+'\Rylume.exe') -ArgumentList $quoted -WorkingDirectory $folder -WindowStyle Hidden -PassThru
}
$swapped=$false;$child=$null
try{
    Log 'Waiting for the previous process to exit'
    $old=Get-Process -Id $plan.parent_pid -ErrorAction SilentlyContinue
    if($old -and -not $old.WaitForExit(90000)){throw 'Previous application is still running; no files replaced'}
    if(Test-Path -LiteralPath $next){throw 'Staging collision'}
    New-Item -ItemType Directory -Path $next | Out-Null
    Get-ChildItem -LiteralPath $stage -Force | Copy-Item -Destination $next -Recurse -Force
    if(Test-Path -LiteralPath $backup){throw 'Backup collision'}
    Move-Item -LiteralPath $target -Destination $backup
    try{Move-Item -LiteralPath $next -Destination $target;$swapped=$true}
    catch{Move-Item -LiteralPath $backup -Destination $target;throw}
    Log 'Starting the new application'
    $child=Launch $target $true
    $healthy=$false
    $healthTimeout=90
    if($plan.health_timeout -and [int]$plan.health_timeout -ge 5 -and [int]$plan.health_timeout -le 120){$healthTimeout=[int]$plan.health_timeout}
    for($i=0;$i -lt $healthTimeout;$i++){
        Start-Sleep -Seconds 1
        if(Test-Path -LiteralPath $plan.health_file){
            $ack=Get-Content -LiteralPath $plan.health_file -Raw | ConvertFrom-Json
            if($ack.nonce -eq $plan.nonce -and $ack.version -eq $plan.version){$healthy=$true;break}
        }
        $child.Refresh();if($child.HasExited){break}
    }
    if(-not $healthy){throw 'New application failed its startup health confirmation'}
    Log 'Update complete; previous application retained as rollback backup'
    @{state='completed';version=$plan.version;backup=$backup} | ConvertTo-Json | Set-Content -LiteralPath ((Split-Path -Parent $planFile)+'\result.json') -Encoding UTF8
    try{if(Within $stage ($data+'\updates\staged')){Remove-Item -LiteralPath $stage -Recurse -Force}}
    catch{Log 'Update succeeded; staging cleanup deferred because a file is busy'}
}catch{
    Log ('Update failed: '+$_.Exception.Message)
    if($swapped){
        if($child -and -not $child.HasExited){$child.Kill();$child.WaitForExit()}
        $failed=$target+'.failed-'+$plan.nonce
        if((Split-Path -Parent $failed) -ne $parent){throw 'Invalid rollback path'}
        Move-Item -LiteralPath $target -Destination $failed
        Move-Item -LiteralPath $backup -Destination $target
        Log 'Previous application restored'
    }
    @{state='rolled_back';message=$_.Exception.Message} | ConvertTo-Json | Set-Content -LiteralPath ((Split-Path -Parent $planFile)+'\result.json') -Encoding UTF8
    if(-not (Get-Process -Id $plan.parent_pid -ErrorAction SilentlyContinue)){Launch $target $false | Out-Null}
    exit 1
}
