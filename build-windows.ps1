# Build Atlas.exe on Windows with PyInstaller.
# Usage (from a Developer PowerShell):  ./build-windows.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "=== Atlas Windows build ===" -ForegroundColor Cyan

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller

# Atlas.spec is platform-aware: on Windows it bundles win32/uiautomation/comtypes
# and produces dist\Atlas\Atlas.exe.
pyinstaller --noconfirm Atlas.spec

Write-Host "`nBuild complete. Output: dist\Atlas\Atlas.exe" -ForegroundColor Green
