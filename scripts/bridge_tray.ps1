# GPT Web MCP Bridge 托盘程序
# 用法: powershell -ExecutionPolicy Bypass -File bridge_tray.ps1 [-SelfTest]
# 关闭(X)/最小化 -> 隐藏到托盘(静默); 托盘菜单: 显示状态 / 开启桥接 / 暂停桥接 / 退出程序
param([switch]$SelfTest)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot "runtime\venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { $Python = (Get-Command python).Source }
$ConfigPath = Join-Path $ProjectRoot "config\config.json"
$IconPath = Join-Path $ProjectRoot "res\GPT_Web_MCP_iconic.png"
$BridgeUrl = "http://127.0.0.1:8765"
$Token = ""
if (Test-Path -LiteralPath $ConfigPath) {
  $cfg = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
  $Token = [string]$cfg.bridge_token
}

$script:BridgeProcess = $null
$script:Exiting = $false
$script:StartedByMe = $false
$script:LastTooltip = ""

function Get-BridgeStatus {
  if (-not $Token) { return $null }
  try {
    $headers = @{ "X-Bridge-Token" = $Token }
    $resp = Invoke-RestMethod -Uri "$BridgeUrl/api/status" -Headers $headers -TimeoutSec 3
    return $resp.status
  } catch { return $null }
}

function Start-BridgeIfNeeded {
  $status = Get-BridgeStatus
  if ($status) { return }
  $env:PYTHONPATH = Join-Path $ProjectRoot "src"
  $script:BridgeProcess = Start-Process -FilePath $Python -ArgumentList "-m", "gpt_web_mcp.bridge" `
    -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru
  $script:StartedByMe = $true
  $deadline = [DateTime]::Now.AddSeconds(12)
  while ([DateTime]::Now -lt $deadline) {
    Start-Sleep -Milliseconds 300
    if (Get-BridgeStatus) { return }
  }
}

function Stop-BridgeGracefully {
  if (-not $Token) { return }
  try {
    $headers = @{ "X-Bridge-Token" = $Token }
    Invoke-RestMethod -Method Post -Uri "$BridgeUrl/api/shutdown" -Headers $headers -TimeoutSec 3 | Out-Null
  } catch {}
  Start-Sleep -Milliseconds 800
  if ($script:BridgeProcess -and -not $script:BridgeProcess.HasExited) {
    try { Stop-Process -Id $script:BridgeProcess.Id -Force -ErrorAction SilentlyContinue } catch {}
  }
}

function Update-StatusWindow {
  $status = Get-BridgeStatus
  if (-not $status) {
    $lblBridge.Text = "Bridge: 离线"
    $lblBridge.ForeColor = [System.Drawing.Color]::Firebrick
    $lblExtension.Text = "扩展: -"
    $lblPage.Text = "页面: -"
    $lblTab.Text = "绑定: -"
    $lblState.Text = "状态: offline"
    $lblError.Text = "Bridge 未运行。点托盘菜单「开启桥接」。"
    Set-TrayTooltip "GPT Web MCP: 离线"
    return
  }
  $lblBridge.Text = "Bridge: 在线 v" + $status.bridge_version
  $lblBridge.ForeColor = [System.Drawing.Color]::SeaGreen
  $lblExtension.Text = "扩展: " + $status.extension
  $lblPage.Text = "页面: " + $status.page
  $lblTab.Text = "绑定: " + $(if ($status.tab_bound) { $status.target_id } else { "未绑定" })
  $lblState.Text = "状态: " + $status.response_state
  $tabCount = @($status.chatgpt_tabs).Count
  $lblError.Text = "ChatGPT 标签页: $tabCount 个; 活动任务: $($status.active_jobs)"
  Set-TrayTooltip ("GPT Web MCP: " + $status.extension + " / " + $status.page + " / " + $status.response_state)
}

function Set-TrayTooltip([string]$text) {
  if ($text -eq $script:LastTooltip) { return }
  $script:LastTooltip = $text
  try { $notify.Text = $text } catch {}
}

# ---------- 控件 ----------
$form = New-Object System.Windows.Forms.Form
$form.Text = "GPT Web MCP Bridge"
$form.Width = 420
$form.Height = 240
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$form.MaximizeBox = $false
$form.StartPosition = "CenterScreen"
$form.ShowInTaskbar = $true

$font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)
$form.Font = $font

$lblBridge = New-Object System.Windows.Forms.Label
$lblBridge.Location = New-Object System.Drawing.Point(16, 14)
$lblBridge.Size = New-Object System.Drawing.Size(380, 22)
$lblBridge.Text = "Bridge: -"
$form.Controls.Add($lblBridge)

$lblExtension = New-Object System.Windows.Forms.Label
$lblExtension.Location = New-Object System.Drawing.Point(16, 40)
$lblExtension.Size = New-Object System.Drawing.Size(380, 22)
$lblExtension.Text = "扩展: -"
$form.Controls.Add($lblExtension)

$lblPage = New-Object System.Windows.Forms.Label
$lblPage.Location = New-Object System.Drawing.Point(16, 66)
$lblPage.Size = New-Object System.Drawing.Size(380, 22)
$lblPage.Text = "页面: -"
$form.Controls.Add($lblPage)

$lblTab = New-Object System.Windows.Forms.Label
$lblTab.Location = New-Object System.Drawing.Point(16, 92)
$lblTab.Size = New-Object System.Drawing.Size(380, 22)
$lblTab.Text = "绑定: -"
$form.Controls.Add($lblTab)

$lblState = New-Object System.Windows.Forms.Label
$lblState.Location = New-Object System.Drawing.Point(16, 118)
$lblState.Size = New-Object System.Drawing.Size(380, 22)
$lblState.Text = "状态: -"
$form.Controls.Add($lblState)

$lblError = New-Object System.Windows.Forms.Label
$lblError.Location = New-Object System.Drawing.Point(16, 144)
$lblError.Size = New-Object System.Drawing.Size(380, 34)
$lblError.ForeColor = [System.Drawing.Color]::DimGray
$lblError.Text = ""
$form.Controls.Add($lblError)

$btnRefresh = New-Object System.Windows.Forms.Button
$btnRefresh.Location = New-Object System.Drawing.Point(16, 182)
$btnRefresh.Size = New-Object System.Drawing.Size(100, 28)
$btnRefresh.Text = "刷新"
$btnRefresh.Add_Click({ Update-StatusWindow })
$form.Controls.Add($btnRefresh)

# ---------- 托盘 ----------
$notify = New-Object System.Windows.Forms.NotifyIcon
if (Test-Path -LiteralPath $IconPath) {
  try {
    $img = [System.Drawing.Image]::FromFile($IconPath)
    $bmp = New-Object System.Drawing.Bitmap $img
    $hicon = $bmp.GetHicon()
    $icon = [System.Drawing.Icon]::FromHandle($hicon)
    $notify.Icon = $icon
    $form.Icon = $icon
  } catch { }
}

$menu = New-Object System.Windows.Forms.ContextMenuStrip
$itemShow = New-Object System.Windows.Forms.ToolStripMenuItem("显示状态")
$itemStart = New-Object System.Windows.Forms.ToolStripMenuItem("开启桥接")
$itemStop = New-Object System.Windows.Forms.ToolStripMenuItem("暂停桥接")
$itemExit = New-Object System.Windows.Forms.ToolStripMenuItem("退出程序")
$menu.Items.Add($itemShow) | Out-Null
$menu.Items.Add($itemStart) | Out-Null
$menu.Items.Add($itemStop) | Out-Null
$menu.Items.Add($itemExit) | Out-Null
$notify.ContextMenuStrip = $menu
$notify.Text = "GPT Web MCP Bridge"
$notify.Visible = $true

$itemShow.Add_Click({
  $form.Show()
  $form.WindowState = "Normal"
  $form.ShowInTaskbar = $true
  $form.Activate()
  Update-StatusWindow
})
$itemStart.Add_Click({
  Start-BridgeIfNeeded
  Start-Sleep -Milliseconds 300
  Update-StatusWindow
})
$itemStop.Add_Click({ Stop-BridgeGracefully; Update-StatusWindow })
$itemExit.Add_Click({
  $script:Exiting = $true
  if ($script:StartedByMe) { Stop-BridgeGracefully }
  $notify.Visible = $false
  $notify.Dispose()
  $form.Close()
  $app.ExitThread()
})

$form.Add_FormClosing({
  param($sender, $e)
  if (-not $script:Exiting) {
    $e.Cancel = $true
    $form.Hide()
    $form.ShowInTaskbar = $false
  }
})
$form.Add_Resize({
  if ($form.WindowState -eq "Minimized") {
    $form.Hide()
    $form.ShowInTaskbar = $false
  }
})
$notify.Add_DoubleClick({ $itemShow.PerformClick() })

# 状态窗口可见时才轮询，避免后台耗资源
$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 2000
$timer.Add_Tick({ if ($form.Visible) { Update-StatusWindow } })
$timer.Start()

$app = New-Object System.Windows.Forms.ApplicationContext($form)

if ($SelfTest) {
  Start-Sleep -Milliseconds 1500
  Update-StatusWindow
  "selftest=" + $lblBridge.Text
  $script:Exiting = $true
  $notify.Visible = $false
  $notify.Dispose()
  $form.Close()
  exit 0
}

[System.Windows.Forms.Application]::Run($app)
