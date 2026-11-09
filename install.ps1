# Claude Notch installer for Windows.
#
# One command, no git needed (PowerShell):
#   irm https://raw.githubusercontent.com/aleoniys/claude-notch/main/install.ps1 | iex
#
# Or from a git clone, inside the folder:
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$repo = "aleoniys/claude-notch"

# Run a native program; its stderr warnings (pip prints some) must not abort the script.
function Run($exe) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { & $exe @args 2>&1 | ForEach-Object { "$_" } } finally { $ErrorActionPreference = $old }
}

function Fail($msg) { Write-Host ""; Write-Host "  $msg" -ForegroundColor Red; Write-Host ""; throw $msg }

# 1. A real Python 3.10+ (not the Microsoft Store stub).
$py = $null
foreach ($cand in @("python", "py")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if (-not $cmd -or $cmd.Source -like "*WindowsApps*") { continue }
    $exe = Run $cmd.Source -c "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')" | Select-Object -Last 1
    if ($LASTEXITCODE -eq 0 -and $exe -and (Test-Path $exe.Trim())) { $py = $exe.Trim(); break }
}
if (-not $py) { Fail "Python 3.10+ is needed: https://www.python.org/downloads/  (tick 'Add python.exe to PATH'), then run this again." }
$pyw = Join-Path (Split-Path $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { Fail "pythonw.exe was not found next to $py" }
Write-Host "Python: $py"

# 2. Where the files are: this folder if it is a clone, otherwise download them.
$here = if ($PSCommandPath) { Split-Path -Parent $PSCommandPath } else { $null }
if ($here -and (Test-Path (Join-Path $here "app.py"))) {
    $dir = $here
} else {
    $dir = if ($env:CLAUDE_NOTCH_DIR) { $env:CLAUDE_NOTCH_DIR } else { Join-Path $env:LOCALAPPDATA "claude-notch" }
    Write-Host "Downloading to $dir"
    $zip = Join-Path $env:TEMP "claude-notch.zip"
    Invoke-WebRequest "https://codeload.github.com/$repo/zip/refs/heads/main" -OutFile $zip -UseBasicParsing
    $tmp = Join-Path $env:TEMP ("claude-notch-" + [guid]::NewGuid().ToString("N"))
    Expand-Archive $zip $tmp -Force
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    # Keep the user's own settings and icon when installing over an older copy.
    Get-ChildItem (Join-Path $tmp "claude-notch-main") -Force | Where-Object { $_.Name -notin @("config.json") -and $_.Name -notlike "custom-icon*" } |
        Copy-Item -Destination $dir -Recurse -Force
    Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

# 3. Libraries.
Write-Host "Installing libraries..."
$pipOut = Run $py -m pip install --user --disable-pip-version-check -q -r (Join-Path $dir "requirements.txt")
if ($LASTEXITCODE -ne 0) { $pipOut | Select-Object -Last 15 | Write-Host; Fail "pip could not install the libraries (see above)." }
$imp = Run $py -c "import pystray, PIL, webview"
if ($LASTEXITCODE -ne 0) { $imp | Select-Object -Last 5 | Write-Host; Fail "The libraries did not import. Try: $py -m pip install -r `"$dir\requirements.txt`"" }

# The panel is drawn by Microsoft Edge WebView2 (built into Windows 11; most Windows 10 PCs have it via Edge).
$wv = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
$hasWv = @("HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\$wv", "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\$wv",
           "HKCU:\Software\Microsoft\EdgeUpdate\Clients\$wv") | Where-Object { (Get-ItemProperty $_ -ErrorAction SilentlyContinue).pv }
if (-not $hasWv) {
    Write-Host "  Microsoft Edge WebView2 Runtime is missing. Install it, then start 'Claude Notch':" -ForegroundColor Yellow
    Write-Host "  https://developer.microsoft.com/microsoft-edge/webview2/  (Evergreen Bootstrapper)" -ForegroundColor Yellow
}

# 4. Start menu shortcut.
$app = Join-Path $dir "app.py"
$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Claude Notch.lnk"
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = '"' + $app + '"'
$s.WorkingDirectory = $dir
$s.IconLocation = Join-Path $dir "icon.ico"
$s.Description = "Claude Code notch widget"
$s.Save()

# 5. Start it (a copy that is already running stays the only one).
if (-not $env:CLAUDE_NOTCH_NO_START) { Start-Process $pyw -ArgumentList ('"' + $app + '"') -WorkingDirectory $dir }

Write-Host ""
Write-Host "  Claude Notch is installed in $dir" -ForegroundColor Green
Write-Host "  Start menu: 'Claude Notch'. Start with Windows: right-click the tray icon."
Write-Host ""
