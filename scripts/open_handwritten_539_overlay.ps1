$ErrorActionPreference = "SilentlyContinue"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$docsPath = Join-Path $projectRoot "docs"
$pageUrl = "http://127.0.0.1:8765/handwritten-539-overlay.html"

$serverReady = Test-NetConnection -ComputerName "127.0.0.1" -Port 8765 -InformationLevel Quiet
if (-not $serverReady) {
    $serverArguments = "-m http.server 8765 --directory `"$docsPath`""
    Start-Process -FilePath $pythonPath `
        -ArgumentList $serverArguments `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden
    for ($attempt = 0; $attempt -lt 10; $attempt++) {
        Start-Sleep -Milliseconds 500
        if (Test-NetConnection -ComputerName "127.0.0.1" -Port 8765 -InformationLevel Quiet) {
            break
        }
    }
}

Start-Process $pageUrl
