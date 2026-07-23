[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$projectRoot = Split-Path -Parent $PSScriptRoot
$updateScript = Join-Path $projectRoot "update_data.bat"
Write-Host "此工具只會在你確認後註冊 Windows 工作排程。"
$answer = Read-Host "是否每天上午 9:00 檢查 Numeris 官方資料？(Y/N)"
if ($answer -notin @("Y", "y")) {
    Write-Host "未註冊任何工作排程。"
    exit 0
}
$action = New-ScheduledTaskAction -Execute $updateScript -Argument "all" -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -Daily -At 9am
Register-ScheduledTask -TaskName "Numeris Daily Data Update" -Action $action -Trigger $trigger -Description "Numeris 官方資料每日檢查" | Out-Null
Write-Host "已註冊 Numeris Daily Data Update。"

