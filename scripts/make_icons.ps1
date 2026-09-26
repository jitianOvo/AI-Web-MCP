param()
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$src = Join-Path $root "res\GPT_Web_MCP_iconic.png"
$iconsDir = Join-Path $root "extension\icons"
New-Item -ItemType Directory -Force -Path $iconsDir | Out-Null

$image = [System.Drawing.Image]::FromFile($src)
foreach ($size in @(16, 32, 48, 128)) {
  $bmp = New-Object System.Drawing.Bitmap $size, $size
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
  $g.Clear([System.Drawing.Color]::Transparent)
  # center-crop square region
  $side = [Math]::Min($image.Width, $image.Height)
  $srcRect = New-Object System.Drawing.Rectangle 0, 0, $side, $side
  $dstRect = New-Object System.Drawing.Rectangle 0, 0, $size, $size
  $g.DrawImage($image, $dstRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
  $g.Dispose()
  $bmp.Save((Join-Path $iconsDir "$size.png"), [System.Drawing.Imaging.ImageFormat]::Png)
  $bmp.Dispose()
  "icon=$size.png"
}
# app icon for the EXE / tray
$big = New-Object System.Drawing.Bitmap 256, 256
$g2 = [System.Drawing.Graphics]::FromImage($big)
$g2.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$side = [Math]::Min($image.Width, $image.Height)
$srcRect = New-Object System.Drawing.Rectangle 0, 0, $side, $side
$dstRect = New-Object System.Drawing.Rectangle 0, 0, 256, 256
$g2.DrawImage($image, $dstRect, $srcRect, [System.Drawing.GraphicsUnit]::Pixel)
$g2.Dispose()
$hicon = $big.GetHicon()
$icon = [System.Drawing.Icon]::FromHandle($hicon)
$fs = [System.IO.File]::Create((Join-Path $root "res\GPT_Web_MCP_iconic.ico"))
$icon.Save($fs)
$fs.Close()
$icon.Dispose()
$big.Dispose()
$image.Dispose()
"ico=res/GPT_Web_MCP_iconic.ico"
