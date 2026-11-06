<#
.SYNOPSIS
    Renders icon.svg into the PNG assets the MSIX package needs.
.DESCRIPTION
    Draws every size on one transparent sheet in headless Microsoft Edge, so each PNG is
    rasterised at its real pixel size, then crops them out into MarcFinderExtension/Assets.
#>
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$root = $PSScriptRoot
$assets = Join-Path $root "MarcFinderExtension\Assets"
$svg = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $root "icon.svg")))

# Name, canvas width and height, icon size (centred on a transparent canvas)
$images = @(
    @("Square44x44Logo.scale-200.png", 88, 88, 88),
    @("Square44x44Logo.targetsize-16_altform-unplated.png", 16, 16, 16),
    @("Square44x44Logo.targetsize-24_altform-unplated.png", 24, 24, 24),
    @("Square44x44Logo.targetsize-32_altform-unplated.png", 32, 32, 32),
    @("Square44x44Logo.targetsize-48_altform-unplated.png", 48, 48, 48),
    @("Square44x44Logo.targetsize-256_altform-unplated.png", 256, 256, 256),
    @("Square150x150Logo.scale-200.png", 300, 300, 200),
    @("Wide310x150Logo.scale-200.png", 620, 300, 200),
    @("SplashScreen.scale-200.png", 1240, 600, 300),
    @("LockScreenLogo.scale-200.png", 48, 48, 48),
    @("StoreLogo.png", 50, 50, 50),
    @("Icon.png", 64, 64, 64)  # shown beside results in Command Palette
)

# Stack the images down one column, 10px apart
$y = 0; $boxes = @(); $html = ""
foreach ($img in $images) {
    $name, $w, $h, $s = $img
    $left = [int](($w - $s) / 2); $top = $y + [int](($h - $s) / 2)
    $html += "<img src='data:image/svg+xml;base64,$svg' style='position:absolute;left:${left}px;top:${top}px;width:${s}px;height:${s}px'>"
    $boxes += , @($name, 0, $y, $w, $h)
    $y += $h + 10
}

$tmp = Join-Path ([IO.Path]::GetTempPath()) "marcfinder-icons"
New-Item -ItemType Directory -Force $tmp | Out-Null
$page = Join-Path $tmp "sheet.html"
$shot = Join-Path $tmp "sheet.png"
"<html><body style='margin:0;background:transparent'>$html</body></html>" | Set-Content $page -Encoding utf8
Remove-Item $shot -ErrorAction SilentlyContinue

$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") |
    Where-Object { Test-Path $_ } | Select-Object -First 1
& $edge --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 `
    --default-background-color=00000000 "--window-size=1240,$y" "--screenshot=$shot" "file:///$($page -replace '\\','/')" 2>&1 | Out-Null
for ($i = 0; $i -lt 50 -and -not (Test-Path $shot); $i++) { Start-Sleep -Milliseconds 200 }

$sheet = [System.Drawing.Bitmap]::FromFile($shot)
try {
    foreach ($b in $boxes) {
        $name, $x, $top, $w, $h = $b
        $crop = $sheet.Clone([System.Drawing.Rectangle]::new($x, $top, $w, $h), $sheet.PixelFormat)
        $crop.Save((Join-Path $assets $name), [System.Drawing.Imaging.ImageFormat]::Png)
        $crop.Dispose()
        Write-Host "  $name ${w}x$h"
    }
}
finally { $sheet.Dispose() }
