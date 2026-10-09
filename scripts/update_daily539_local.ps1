$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$dataPath = Join-Path $projectRoot 'docs/data/daily539.json'
$taipei = [TimeZoneInfo]::ConvertTimeBySystemTimeZoneId([DateTime]::UtcNow, 'Taipei Standard Time')
$month = $taipei.AddMonths(-1).ToString('yyyy-MM')
$endMonth = $taipei.ToString('yyyy-MM')
$url = "https://api.taiwanlottery.com/TLCAPIWeB/Lottery/Daily539Result?month=$month&endMonth=$endMonth&pageNum=1&pageSize=500"
$response = Invoke-RestMethod -Uri $url -TimeoutSec 30
if ($response.rtCode -ne 0 -or -not $response.content.daily539Res) { throw '官方資料無法取得，保留原資料。' }
$payload = Get-Content -LiteralPath $dataPath -Raw -Encoding utf8 | ConvertFrom-Json
$merged = @{}
foreach ($draw in $payload.draws) { $merged[[string]$draw.draw_no] = $draw }
foreach ($row in $response.content.daily539Res) {
    $numbers = @($row.drawNumberSize | ForEach-Object { [int]$_ } | Sort-Object)
    if ($numbers.Count -ne 5 -or @($numbers | Select-Object -Unique).Count -ne 5 -or $numbers[0] -lt 1 -or $numbers[-1] -gt 39) { throw '官方獎號驗證失敗，保留原資料。' }
    $date = ([DateTime]::Parse($row.lotteryDate)).ToString('yyyy-MM-dd')
    if ($date -gt $taipei.ToString('yyyy-MM-dd')) { throw '官方資料日期超出今天。' }
    $merged[[string]$row.period] = [pscustomobject]@{ draw_no = [string]$row.period; draw_date = $date; numbers = $numbers; source_status = 'official' }
}
$draws = @($merged.Values | Sort-Object draw_date,draw_no -Descending | Select-Object -First 200)
$before = $payload.draws | ConvertTo-Json -Depth 10 -Compress
$after = $draws | ConvertTo-Json -Depth 10 -Compress
if ($before -eq $after) { Write-Output "資料未變更：$($payload.latest_draw_date)"; exit 0 }
$payload.draws = $draws
$payload.draw_count = $draws.Count
$payload.latest_draw_no = $draws[0].draw_no
$payload.latest_draw_date = $draws[0].draw_date
$payload.generated_at = $taipei.ToString('yyyy-MM-ddTHH:mm:ss') + '+08:00'
$payload.source = '台灣彩券官方資料'
$temporaryPath = "$dataPath.tmp"
$payload | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $temporaryPath -Encoding utf8
Move-Item -LiteralPath $temporaryPath -Destination $dataPath -Force
Write-Output "已更新至 $($payload.latest_draw_date)，共 $($draws.Count) 期。"
