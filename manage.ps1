param([ValidateSet('Start','Open','Status','Stop','EnableStartup','DisableStartup','Shortcut')][string]$Action='Open')
$ErrorActionPreference='Stop'
$url='http://127.0.0.1:8765'
$root=$PSScriptRoot
$task='VideoLibrary-Local-'+$env:USERNAME
$logDir=Join-Path $root 'logs'
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$managerLog=Join-Path $logDir 'startup.log'
trap {
    $detail=($_ | Out-String)
    Add-Content -LiteralPath $managerLog -Value ((Get-Date -Format o)+' '+$detail) -Encoding UTF8
    Write-Host ('启动管理失败。日志：'+$managerLog) -ForegroundColor Red
    Write-Host $detail
    exit 1
}
function Get-LocalPage {
    try { $p=Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 2; if($p.Content -match 'name="local-token" content="([^"]+)"'){return $p} } catch {}
    return $null
}
function Start-Local {
    $mutex=New-Object System.Threading.Mutex($false, 'Local\VideoLibrary-8765-Startup')
    $locked=$false
    try {
        try {$locked=$mutex.WaitOne(30000)} catch [System.Threading.AbandonedMutexException] {$locked=$true}
        if(!$locked){throw '另一个启动操作尚未完成，请稍后重试。'}
        if(Get-LocalPage){return}
        if(Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue){throw '端口 8765 已被其他服务占用，未启动新进程。'}
        $exe=Join-Path $root '.venv\Scripts\python.exe'
        if(!(Test-Path -LiteralPath $exe)){throw '未找到现有虚拟环境 python.exe。'}
        $stamp=(Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,8)
        $outLog=Join-Path $logDir ($stamp+'.stdout.log')
        $errLog=Join-Path $logDir ($stamp+'.stderr.log')
        Add-Content -LiteralPath $managerLog -Encoding UTF8 -Value ((Get-Date -Format o)+' Starting; stdout='+$outLog+'; stderr='+$errLog)
        $process=Start-Process -FilePath $exe -ArgumentList ('-u "'+(Join-Path $root 'app.py')+'"') -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
        for($i=0;$i -lt 60;$i++){
            if(Get-LocalPage){return}
            if($process.HasExited){throw ('后台进程已退出，退出码 '+$process.ExitCode+'。错误日志：'+$errLog)}
            Start-Sleep -Milliseconds 500
        }
        throw ('等待服务超时；未强制终止进程，请检查端口与日志：'+$errLog)
    } finally {
        if($locked){$mutex.ReleaseMutex()}
        $mutex.Dispose()
    }
}
switch($Action){
 'Start' {Start-Local}
 'Open' {Start-Local;Start-Process $url}
 'Status' {if(Get-LocalPage){'VideoLibrary 正在运行'}else{'VideoLibrary 未运行或端口不是本项目'}}
 'Stop' {
    $p=Get-LocalPage
    if(!$p){'服务未运行';break}
    if($p.Content -notmatch 'name="local-token" content="([^"]+)"'){throw '服务校验失败'}
    Invoke-RestMethod "$url/api/stop" -Method Post -ContentType 'application/json' -Body '{}' -Headers @{'X-Local-Token'=$Matches[1]} | Out-Null
    '已请求退出；下载期间会拒绝退出。'
 }
 'EnableStartup' {
    $user=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    $act=New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument ('-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "'+(Join-Path $root 'manage.ps1')+'" -Action Start') -WorkingDirectory $root
    $trigger=New-ScheduledTaskTrigger -AtLogOn -User $user
    $principal=New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    $settings=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $task -Action $act -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
    '已启用登录自启，不打开浏览器。'
 }
 'DisableStartup' {Unregister-ScheduledTask -TaskName $task -Confirm:$false -ErrorAction SilentlyContinue;'已关闭登录自启。'}
 'Shortcut' {
    $shell=New-Object -ComObject WScript.Shell
    $link=$shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'VideoLibrary 视频保存.lnk'))
    $link.TargetPath="$env:SystemRoot\System32\wscript.exe"
    $link.Arguments='"'+(Join-Path $root 'open.vbs')+'"'
    $link.WorkingDirectory=$root
    $link.Save()
    '已创建桌面快捷方式。'
 }
}
