# PipeFlow Packaging

PipeFlow is packaged with PyInstaller. Current release version: `1.1`.

## Mac

Run this on a Mac:

```bash
./build_mac_app.sh
```

The build creates:

- `release/mac/PipeFlow.app`
- `release/PipeFlow-mac-v1.1.dmg`

## Windows

PyInstaller Windows executables need to be built on Windows. Copy this project to a Windows laptop with Python installed, then run PowerShell from the project folder:

```powershell
.\build_windows_exe.ps1
```

The build creates:

- `release\windows\PipeFlow.exe`
- `release\PipeFlow-windows-v1.1.zip`

## Data Location

Each user gets their own local database at:

- Mac: `/Users/<user>/PipeFlow/pipeflow.db`
- Windows: `C:\Users\<user>\PipeFlow\pipeflow.db`

The packaged app starts a local web server and opens PipeFlow in the user's default browser.
