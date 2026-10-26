# Captures the LinkedIn/README screenshots with a headless Chromium browser (Edge or Chrome).
# Prerequisite: the app is running on http://localhost:3000 with a completed forecast run
# (the journey pages "Relatorio" and "Desvios" are locked until the model competition finishes).
#
#   powershell -ExecutionPolicy Bypass -File scripts/capture_screenshots.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/capture_screenshots.ps1 -Only entrada,desvios-plano
#
# Screens: the 3-stage journey (Entrada -> Relatorio executivo -> Desvios) plus the tools.
# Screenshots of screens that no longer exist (overview, sop-cockpit, fva) are removed.
#
# ForecastLab - Developed by Wallison Sampaio (https://www.linkedin.com/in/wallisonsampaio)

param(
    [string]$BaseUrl = "http://localhost:3000",
    [int]$Width = 1440,
    [int]$Height = 900,
    [string[]]$Only = @()
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

# file name (without .png) -> route
$pages = [ordered]@{
    # Landing page
    "home"               = "/"
    # Journey: stage 1, 2 and 3
    "entrada"            = "/app/entrada"
    "relatorio-resumo"   = "/app/relatorio/resumo"
    "relatorio-gap"      = "/app/relatorio/gap"
    "desvios-plano"      = "/app/desvios?cmp=fc_pl&nivel=customer"
    "desvios-previsao"   = "/app/desvios?lente=previsao"
    # Tools and governance
    "forecast-workspace" = "/app/forecasting"
    "scenarios"          = "/app/scenarios"
    "model-performance"  = "/app/models"
    "ai-analyst"         = "/app/ai?q=A%20meta%20%C3%A9%20realista%3F"
    "alerts"             = "/app/alerts"
}

# "-Only a,b" arrives as one string when the script is started with -File: split it.
$Only = @($Only | ForEach-Object { $_ -split "," } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$unknown = @($Only | Where-Object { -not $pages.Contains($_) })
if ($unknown.Count -gt 0) { throw "Unknown screen(s): $($unknown -join ', '). Use: $($pages.Keys -join ', ')" }

# Screens replaced by the journey: drop their old captures so they are not published by mistake.
$obsolete = @("overview", "sop-cockpit", "fva")
foreach ($name in $obsolete) {
    $old = Join-Path $out "$name.png"
    if (Test-Path $old) {
        Remove-Item $old
        Write-Host "removed obsolete $name.png"
    }
}

foreach ($name in $pages.Keys) {
    if ($Only.Count -gt 0 -and $Only -notcontains $name) { continue }
    $file = Join-Path (Resolve-Path $out) "$name.png"
    $url = "$BaseUrl$($pages[$name])"
    & $browser --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 `
        "--window-size=$Width,$Height" --virtual-time-budget=20000 "--screenshot=$file" $url 2>$null | Out-Null
    Write-Host "captured $name -> $file"
}
