# Captures the LinkedIn/README screenshots with a headless Chromium browser (Edge or Chrome).
# Prerequisite: the app is running on http://localhost:3000 with a completed forecast run.
#
#   powershell -ExecutionPolicy Bypass -File scripts/capture_screenshots.ps1
#
# ForecastLab - Developed by Wallison Sampaio (https://www.linkedin.com/in/wallisonsampaio)

param(
    [string]$BaseUrl = "http://localhost:3000",
    [int]$Width = 1440,
    [int]$Height = 900
)

$browsers = @(
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe"
)
$browser = $browsers | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) { throw "Edge or Chrome not found." }

$out = Join-Path $PSScriptRoot "..\screenshots"
New-Item -ItemType Directory -Force -Path $out | Out-Null

$pages = [ordered]@{
    "home"               = "/"
    "overview"           = "/app/overview"
    "sop-cockpit"        = "/app/sop"
    "forecast-workspace" = "/app/forecasting"
    "model-performance"  = "/app/models"
    "scenarios"          = "/app/scenarios"
    "fva"                = "/app/fva"
    "ai-analyst"         = "/app/ai?q=Is%20December%20target%20realistic%3F"
    "data-health"        = "/app/data"
    "alerts"             = "/app/alerts"
}

foreach ($name in $pages.Keys) {
    $file = Join-Path (Resolve-Path $out) "$name.png"
    $url = "$BaseUrl$($pages[$name])"
    & $browser --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 `
        "--window-size=$Width,$Height" --virtual-time-budget=20000 "--screenshot=$file" $url 2>$null | Out-Null
    Write-Host "captured $name -> $file"
}
