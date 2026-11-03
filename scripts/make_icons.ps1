param()
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$root = Split-Path -Parent $PSScriptRoot
$iconsDir = Join-Path $root 'extension\icons'
New-Item -ItemType Directory -Force -Path $iconsDir | Out-Null

function Render-Icon([int]$size) {
    $canvas = [System.Drawing.Bitmap]::new(1024, 1024)
    $g = [System.Drawing.Graphics]::FromImage($canvas)
    $g.SmoothingMode = 'AntiAlias'
    $g.Clear([System.Drawing.Color]::Transparent)
    $g.ScaleTransform(4, 4)
    $tile = [System.Drawing.Drawing2D.GraphicsPath]::new()
    foreach ($arc in @(@(8,8,56,56,180,90),@(192,8,56,56,270,90),@(192,192,56,56,0,90),@(8,192,56,56,90,90))) {
        $tile.AddArc($arc[0],$arc[1],$arc[2],$arc[3],$arc[4],$arc[5])
    }
    $tile.CloseFigure()
    $fill = [System.Drawing.Drawing2D.LinearGradientBrush]::new([System.Drawing.Point]::new(24,16),[System.Drawing.Point]::new(232,248),[System.Drawing.Color]::FromArgb(45,56,112),[System.Drawing.Color]::FromArgb(14,20,44))
    $g.FillPath($fill,$tile)
    $pen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(244,248,255),17)
    $pen.StartCap = 'Round'; $pen.EndCap = 'Round'; $pen.LineJoin = 'Round'
    $a = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $a.AddArc(54,62,92,92,90,180)
    $a.AddLine(100,62,151,62)
    $a.AddArc(128,62,44,44,270,90)
    $a.AddLine(172,84,172,119)
    $g.DrawPath($pen,$a)
    $b = [System.Drawing.Drawing2D.GraphicsPath]::new()
    $b.AddArc(110,102,92,92,270,180)
    $b.AddLine(156,194,105,194)
    $b.AddArc(84,150,44,44,90,90)
    $b.AddLine(84,172,84,137)
    $g.DrawPath($pen,$b)
    $accent = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(79,224,192))
    $g.FillEllipse($accent,114,114,28,28)
    $g.Dispose()
    $result = [System.Drawing.Bitmap]::new($size,$size)
    $scaled = [System.Drawing.Graphics]::FromImage($result)
    $scaled.InterpolationMode = 'HighQualityBicubic'
    $scaled.DrawImage($canvas,0,0,$size,$size)
    $scaled.Dispose(); $canvas.Dispose()
    $tile.Dispose(); $fill.Dispose(); $pen.Dispose(); $a.Dispose(); $b.Dispose(); $accent.Dispose()
    return ,$result
}
$master = Render-Icon 1024
$master.Save((Join-Path $root 'res\GPT_Web_MCP_iconic.png'),[System.Drawing.Imaging.ImageFormat]::Png)
$master.Dispose()
$entries = @()
foreach ($size in @(16,24,32,48,64,128,256)) {
    $bmp = Render-Icon $size
    $stream = [System.IO.MemoryStream]::new()
    $bmp.Save($stream,[System.Drawing.Imaging.ImageFormat]::Png)
    if ($size -in @(16,32,48,128)) { [System.IO.File]::WriteAllBytes((Join-Path $iconsDir "$size.png"),$stream.ToArray()) }
    $entries += @{ Size=$size; Data=$stream.ToArray() }
    $stream.Dispose(); $bmp.Dispose()
}
$file = [System.IO.File]::Create((Join-Path $root 'res\GPT_Web_MCP_iconic.ico'))
$writer = [System.IO.BinaryWriter]::new($file)
$writer.Write([uint16]0); $writer.Write([uint16]1); $writer.Write([uint16]$entries.Count)
$offset = 6 + 16 * $entries.Count
foreach ($entry in $entries) {
    $dimension = if ($entry.Size -eq 256) { 0 } else { $entry.Size }
    $writer.Write([byte]$dimension); $writer.Write([byte]$dimension)
    $writer.Write([byte]0); $writer.Write([byte]0)
    $writer.Write([uint16]1); $writer.Write([uint16]32)
    $writer.Write([uint32]$entry.Data.Length); $writer.Write([uint32]$offset)
    $offset += $entry.Data.Length
}
foreach ($entry in $entries) { $writer.Write([byte[]]$entry.Data) }
$writer.Dispose()
Write-Output 'icons=generated (16,24,32,48,64,128,256)'
