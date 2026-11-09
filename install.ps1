# Installs the libraries, adds a Start menu shortcut and starts the notch.
# Usage (PowerShell, in this folder):  powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$py = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $py) { Write-Host "Python 3.10+ is required: https://www.python.org/downloads/ (tick 'Add to PATH')"; exit 1 }
$pyw = Join-Path (Split-Path $py) "pythonw.exe"

& $py -m pip install --user -r (Join-Path $here "requirements.txt")

$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Claude Notch.lnk"
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
$s.TargetPath = $pyw
$s.Arguments = '"' + (Join-Path $here "app.py") + '"'
$s.WorkingDirectory = $here
$s.IconLocation = Join-Path $here "icon.ico"
$s.Description = "Claude Code notch widget"
$s.Save()

Start-Process $pyw -ArgumentList ('"' + (Join-Path $here "app.py") + '"') -WorkingDirectory $here
Write-Host "Done. Start menu: 'Claude Notch'. Autostart: right-click the tray icon > Start with Windows."
