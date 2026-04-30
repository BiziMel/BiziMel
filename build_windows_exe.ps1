$ErrorActionPreference = "Stop"
$Version = "1.0"
$env:PYINSTALLER_CONFIG_DIR = Join-Path (Get-Location) "release\pyinstaller-cache"
New-Item -ItemType Directory -Force -Path $env:PYINSTALLER_CONFIG_DIR | Out-Null

py -m pip install --upgrade pyinstaller flask
py -m PyInstaller --noconfirm --distpath release\windows --workpath release\build-windows PipeFlow_windows.spec

Compress-Archive -Path release\windows\PipeFlow.exe -DestinationPath "release\PipeFlow-windows-v$Version.zip" -Force
